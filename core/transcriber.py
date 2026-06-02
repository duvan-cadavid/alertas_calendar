import os
import subprocess
import tempfile

from PyQt6.QtCore import QThread, pyqtSignal


class TranscriberThread(QThread):
    """Transcribe a video file to Spanish text using Groq Whisper API.

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
    MAX_MB = 24   # Groq limit is 25 MB — keep a 1 MB margin

    def __init__(self, media_path: str, api_key: str, parent=None):
        super().__init__(parent)
        self._path = media_path
        self._api_key = api_key

    def run(self):
        tmp_audio = None
        try:
            # ── Validate API key early ──────────────────────────────
            if not self._api_key or not self._api_key.strip().startswith('gsk_'):
                self.error.emit(
                    'API key de Groq inválida o no configurada.\n'
                    'Ve a ⚙ Configuración → Transcripción e IA y pega tu clave.'
                )
                return

            # ── Extract audio ───────────────────────────────────────
            self.progress.emit('Extrayendo audio…')
            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp_audio = tmp.name
            tmp.close()

            r = subprocess.run(
                ['ffmpeg', '-y', '-i', self._path,
                 '-vn', '-acodec', 'libmp3lame', '-ab', '32k', '-ar', '16000',
                 tmp_audio],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                raise RuntimeError('No se pudo extraer el audio del video.')

            size_mb = os.path.getsize(tmp_audio) / (1024 * 1024)
            if size_mb > self.MAX_MB:
                raise RuntimeError(
                    f'El audio ({size_mb:.1f} MB) supera el límite de Groq '
                    f'({self.MAX_MB} MB). Graba en segmentos más cortos.'
                )

            # ── Transcribe via Groq ─────────────────────────────────
            self.progress.emit('Transcribiendo con Groq Whisper…')
            from groq import Groq
            client = Groq(api_key=self._api_key.strip())

            with open(tmp_audio, 'rb') as f:
                audio_bytes = f.read()

            result = client.audio.transcriptions.create(
                file=('audio.mp3', audio_bytes),
                model=self.MODEL,
                language='es',
                response_format='verbose_json',
                timestamp_granularities=['segment'],
            )

            # ── Parse response ──────────────────────────────────────
            # Groq returns Transcription(extra='allow'):
            #   result.text     → full transcript string (always present)
            #   result.segments → list of dicts with 'start', 'end', 'text'
            #                     (present when verbose_json + segment granularity)
            transcription = self._parse(result)
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
    def _parse(result) -> str:
        """Extract timestamped lines from a Groq transcription result.

        Segments are always dicts in groq 1.4.0 (Pydantic extra='allow').
        Falls back to result.text if no segments are present.
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
            mins, secs = divmod(int(start), 60)
            lines.append(f'[{mins:02d}:{secs:02d}] {text}')

        if not lines:
            # Fallback: no segments — use plain text without timestamps
            lines.append(getattr(result, 'text', '').strip())

        return '\n'.join(lines)

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
