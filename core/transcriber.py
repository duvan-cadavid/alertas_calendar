import os
import subprocess
import sys
import tempfile

from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_config import get_groq_api_key
from core.recorder import _get_ffmpeg_exe


class TranscriberThread(QThread):
    """Transcribe a video file to Spanish text using Groq Whisper API.

    Long recordings (clients reported ~40+ min meetings coming back cut off,
    or the summary step failing right after) go through Whisper in
    _CHUNK_SECONDS pieces instead of one request for the whole file:

    - It keeps every request tiny and fast regardless of meeting length —
      at 32 kbps a 10-minute chunk is ~2.4 MB, nowhere near Groq's 25 MB
      per-file cap (a single 100+ minute recording could hit that in one
      shot, which the old whole-file MAX_MB check only warned about instead
      of avoiding).
    - It caps how many transcription tokens land in the same request, which
      is what actually keeps the DOWNSTREAM summarizer call (same Groq
      account, shared tokens-per-minute budget) from getting rate-limited
      right after a long transcription finishes — see core/summarizer.py's
      own chunking for the other half of that fix.

    Validated against groq 1.4.0:
    - Segments are returned as dicts: {'start': float, 'end': float, 'text': str, ...}
    - result.text always contains the full transcription as a fallback
    - response_format='verbose_json' + timestamp_granularities=['segment']
      gives per-segment timestamps via result.segments (list of dicts)
    """
    progress = pyqtSignal(str)
    done = pyqtSignal(str)   # timestamped transcription text
    error = pyqtSignal(str)

    MODEL = 'whisper-large-v3-turbo'
    MAX_MB = 24            # Groq limit is 25 MB — keep a 1 MB margin
    CHUNK_SECONDS = 600    # 10 min per Whisper request

    def __init__(self, media_path: str, parent=None):
        super().__init__(parent)
        self._path = media_path
        self._api_key = get_groq_api_key()

    def run(self):
        tmp_audio = None
        try:
            # ── Extract audio ───────────────────────────────────────
            self.progress.emit('Extrayendo audio…')
            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp_audio = tmp.name
            tmp.close()

            r = subprocess.run(
                [_get_ffmpeg_exe(), '-y', '-i', self._path,
                 '-vn', '-acodec', 'libmp3lame', '-ab', '32k', '-ar', '16000',
                 tmp_audio],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                raise RuntimeError('No se pudo extraer el audio del video.')

            duration = self._probe_duration(tmp_audio)
            from groq import Groq
            client = Groq(api_key=self._api_key.strip())

            chunk_bounds = self._chunk_bounds(duration)
            lines = []
            for i, (start, end) in enumerate(chunk_bounds, start=1):
                self.progress.emit(
                    f'Transcribiendo con Groq Whisper… parte {i}/{len(chunk_bounds)}'
                    if len(chunk_bounds) > 1 else 'Transcribiendo con Groq Whisper…'
                )
                chunk_path = self._extract_chunk(tmp_audio, start, end - start) \
                    if len(chunk_bounds) > 1 else tmp_audio
                try:
                    size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
                    if size_mb > self.MAX_MB:
                        raise RuntimeError(
                            f'Un fragmento de audio ({size_mb:.1f} MB) supera el límite '
                            f'de Groq ({self.MAX_MB} MB) incluso partido en '
                            f'{self.CHUNK_SECONDS // 60} min.'
                        )
                    with open(chunk_path, 'rb') as f:
                        audio_bytes = f.read()
                    result = client.audio.transcriptions.create(
                        file=('audio.mp3', audio_bytes),
                        model=self.MODEL,
                        language='es',
                        response_format='verbose_json',
                        timestamp_granularities=['segment'],
                    )
                    lines.extend(self._parse(result, offset=start))
                finally:
                    if chunk_path != tmp_audio and os.path.exists(chunk_path):
                        try:
                            os.unlink(chunk_path)
                        except Exception:
                            pass

            transcription = '\n'.join(lines)
            if not transcription.strip():
                self.error.emit(
                    'La transcripción está vacía. '
                    'Verifica que el audio tenga voz audible.'
                )
                return

            self.done.emit(transcription)

        except ImportError:
            self.error.emit(
                'El módulo de transcripción no está disponible.\n'
                'Reinicia la aplicación para instalar las dependencias automáticamente.'
            )
        except Exception as e:
            self.error.emit(self._friendly_error(e))
        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.unlink(tmp_audio)
                except Exception:
                    pass

    @staticmethod
    def _probe_duration(audio_path: str) -> float:
        """Duración en segundos vía ffprobe; si falla, asume un solo fragmento."""
        try:
            ffprobe = _get_ffmpeg_exe().replace('ffmpeg', 'ffprobe')
            r = subprocess.run(
                [ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                capture_output=True, text=True, timeout=30,
            )
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    def _chunk_bounds(self, duration: float) -> list:
        """Lista de (inicio, fin) en segundos. Un solo tramo si dura poco o
        no se pudo medir la duración (ffprobe falló → se manda entero, como
        antes de este cambio)."""
        if duration <= 0 or duration <= self.CHUNK_SECONDS:
            return [(0, duration or 0)]
        bounds = []
        start = 0.0
        while start < duration:
            end = min(start + self.CHUNK_SECONDS, duration)
            bounds.append((start, end))
            start = end
        return bounds

    @staticmethod
    def _extract_chunk(audio_path: str, start: float, length: float) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        chunk_path = tmp.name
        tmp.close()
        r = subprocess.run(
            [_get_ffmpeg_exe(), '-y', '-i', audio_path,
             '-ss', str(start), '-t', str(length),
             '-acodec', 'copy', chunk_path],
            capture_output=True, timeout=60,
        )
        if r.returncode != 0:
            raise RuntimeError('No se pudo partir el audio en fragmentos.')
        return chunk_path

    @staticmethod
    def _parse(result, offset: float = 0.0) -> list:
        """Extract timestamped lines from a Groq transcription result.

        Segments are always dicts in groq 1.4.0 (Pydantic extra='allow').
        Falls back to result.text if no segments are present. ``offset`` is
        the chunk's start time in the full recording, added to every segment
        so timestamps stay correct across chunk boundaries.
        """
        segments = getattr(result, 'segments', None) or []
        lines = []
        for seg in segments:
            if isinstance(seg, dict):
                start = seg.get('start', 0)
                text  = seg.get('text', '').strip()
            else:
                # Future-proof: handle object-style segments
                start = getattr(seg, 'start', 0)
                text  = getattr(seg, 'text', '').strip()
            if not text:
                continue
            mins, secs = divmod(int(start + offset), 60)
            lines.append(f'[{mins:02d}:{secs:02d}] {text}')

        if not lines:
            # Fallback: no segments — use plain text without timestamps
            text = getattr(result, 'text', '').strip()
            if text:
                mins, secs = divmod(int(offset), 60)
                lines.append(f'[{mins:02d}:{secs:02d}] {text}')

        return lines

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        """Map Groq API exceptions to user-friendly Spanish messages."""
        name = type(exc).__name__
        msg  = str(exc)

        if 'AuthenticationError' in name or '401' in msg:
            return (
                'API key de Groq inválida o expirada.\n'
                'Ve a console.groq.com para verificar tu clave.'
            )
        if 'RateLimitError' in name or '429' in msg:
            return (
                'Límite de uso de Groq alcanzado.\n'
                'Espera unos minutos e intenta de nuevo, o revisa tu plan en console.groq.com.'
            )
        if 'BadRequestError' in name or '400' in msg:
            return f'El archivo de audio no pudo procesarse: {msg[:200]}'
        if 'APIConnectionError' in name or 'connection' in msg.lower():
            return (
                'No se pudo conectar a Groq. '
                'Verifica tu conexión a internet.'
            )
        if 'APITimeoutError' in name or 'timeout' in msg.lower():
            return 'Tiempo de espera agotado al conectar con Groq. Intenta de nuevo.'
        return f'Error de transcripción: {msg[:300]}'
