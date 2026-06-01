from PyQt6.QtCore import QThread, pyqtSignal


class TranscriberThread(QThread):
    """Transcribe a video/audio file to Spanish text using faster-whisper."""
    progress = pyqtSignal(str)
    done = pyqtSignal(str)   # timestamped transcription text
    error = pyqtSignal(str)

    MODEL = 'medium'

    def __init__(self, media_path: str, parent=None):
        super().__init__(parent)
        self._path = media_path

    def run(self):
        try:
            self.progress.emit('Cargando modelo Whisper… (primera vez descarga ~1.5 GB)')
            from faster_whisper import WhisperModel
            model = WhisperModel(self.MODEL, device='cpu', compute_type='int8')
            self.progress.emit('Transcribiendo audio en español…')
            segments, _ = model.transcribe(
                self._path,
                language='es',
                beam_size=5,
                vad_filter=True,
                vad_parameters={'min_silence_duration_ms': 500},
            )
            lines = []
            for seg in segments:
                mins, secs = divmod(int(seg.start), 60)
                lines.append(f'[{mins:02d}:{secs:02d}] {seg.text.strip()}')
            self.done.emit('\n'.join(lines))
        except ImportError:
            self.error.emit(
                'faster-whisper no está instalado.\n'
                'Ejecuta:  pip install faster-whisper'
            )
        except Exception as e:
            self.error.emit(str(e))
