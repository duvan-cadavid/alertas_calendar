import os
import subprocess
import tempfile

from PyQt6.QtCore import QThread, pyqtSignal


class TranscriberThread(QThread):
    """Transcribe a video file to Spanish text using Groq Whisper API."""
    progress = pyqtSignal(str)
    done = pyqtSignal(str)   # timestamped transcription text
    error = pyqtSignal(str)

    def __init__(self, media_path: str, api_key: str, parent=None):
        super().__init__(parent)
        self._path = media_path
        self._api_key = api_key

    def run(self):
        tmp_audio = None
        try:
            self.progress.emit('Extrayendo audio…')
            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp_audio = tmp.name
            tmp.close()

            # 32k bitrate keeps audio under 25 MB/hora (límite de Groq)
            r = subprocess.run(
                ['ffmpeg', '-y', '-i', self._path,
                 '-vn', '-acodec', 'libmp3lame', '-ab', '32k', '-ar', '16000',
                 tmp_audio],
                capture_output=True, timeout=120,
            )
            if r.returncode != 0:
                raise RuntimeError('No se pudo extraer el audio del video.')

            size_mb = os.path.getsize(tmp_audio) / (1024 * 1024)
            if size_mb > 24:
                raise RuntimeError(
                    f'El audio ({size_mb:.1f} MB) supera el límite de Groq (25 MB). '
                    'Divide la grabación en segmentos más cortos.'
                )

            self.progress.emit('Transcribiendo con Groq Whisper…')
            from groq import Groq
            client = Groq(api_key=self._api_key)

            with open(tmp_audio, 'rb') as f:
                result = client.audio.transcriptions.create(
                    file=('audio.mp3', f.read()),
                    model='whisper-large-v3-turbo',
                    language='es',
                    response_format='verbose_json',
                    timestamp_granularities=['segment'],
                )

            lines = []
            if hasattr(result, 'segments') and result.segments:
                for seg in result.segments:
                    mins, secs = divmod(int(seg.start), 60)
                    lines.append(f'[{mins:02d}:{secs:02d}] {seg.text.strip()}')
            else:
                lines.append(result.text)

            self.done.emit('\n'.join(lines))

        except ImportError:
            self.error.emit('groq no instalado. Ejecuta: pip install groq')
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.unlink(tmp_audio)
                except Exception:
                    pass
