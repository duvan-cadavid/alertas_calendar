import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QTextEdit, QFrame, QSizePolicy,
)

from config.settings import Config
from core.recorder import ScreenRecorder, ScreenInfo, get_screens, get_audio_devices, ffmpeg_available
from core.transcriber import TranscriberThread
from core.summarizer import SummarizerThread

_STYLE = """
QWidget {
    background-color: #11111b;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Ubuntu', Arial, sans-serif;
    font-size: 13px;
}
QComboBox {
    background-color: #1e1e2e; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px; padding: 6px 10px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #1e1e2e; color: #cdd6f4;
    selection-background-color: #313244;
}
QCheckBox { color: #cdd6f4; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #45475a; background: #1e1e2e;
}
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QLineEdit {
    background-color: #1e1e2e; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px; padding: 6px 10px;
}
QLineEdit:focus { border-color: #89b4fa; }
QPushButton#btn_browse {
    background-color: #1e1e2e; color: #a6adc8;
    border: 1px solid #313244; border-radius: 6px; padding: 6px 12px;
}
QPushButton#btn_browse:hover { background-color: #313244; }
QPushButton#btn_start {
    background-color: #1e3a5f; color: #89b4fa;
    border: 1px solid #89b4fa; border-radius: 8px;
    padding: 11px 28px; font-size: 14px; font-weight: bold;
}
QPushButton#btn_start:hover  { background-color: #264a73; }
QPushButton#btn_start:disabled { background-color: #181825; color: #45475a; border-color: #313244; }
QPushButton#btn_pause {
    background-color: #2e1a06; color: #fb923c;
    border: 1px solid #fb923c; border-radius: 8px;
    padding: 11px 28px; font-size: 14px; font-weight: bold;
}
QPushButton#btn_pause:hover { background-color: #3d2209; }
QPushButton#btn_resume {
    background-color: #0a2e1a; color: #4ade80;
    border: 1px solid #4ade80; border-radius: 8px;
    padding: 11px 28px; font-size: 14px; font-weight: bold;
}
QPushButton#btn_resume:hover { background-color: #0d3d22; }
QPushButton#btn_stop {
    background-color: #2e1a1a; color: #f38ba8;
    border: 1px solid #f38ba8; border-radius: 8px;
    padding: 11px 28px; font-size: 14px; font-weight: bold;
}
QPushButton#btn_stop:hover { background-color: #3d2222; }
QPushButton#btn_copy {
    background-color: #1e1e2e; color: #89b4fa;
    border: 1px solid #313244; border-radius: 6px; padding: 5px 14px; font-size: 12px;
}
QPushButton#btn_copy:hover { background-color: #313244; }
QTextEdit {
    background-color: #1e1e2e; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 8px; padding: 8px; font-size: 12px;
}
QScrollBar:vertical {
    background: #181825; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet('background-color: #313244;')
    line.setFixedHeight(1)
    return line


def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet('font-size: 11px; color: #6c7086; letter-spacing: 1px;')
    return lbl


class RecorderWindow(QWidget):

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle('Grabación de Pantalla')
        self.setMinimumSize(580, 660)
        self.resize(620, 740)
        self.setStyleSheet(_STYLE)

        self._recorder = ScreenRecorder(self)
        self._recorder.recording_started.connect(self._on_started)
        self._recorder.paused.connect(self._on_paused)
        self._recorder.resumed.connect(self._on_resumed)
        self._recorder.finished.connect(self._on_finished)
        self._recorder.error.connect(self._on_error)

        self._transcriber: Optional[TranscriberThread] = None
        self._summarizer: Optional[SummarizerThread] = None
        self._screens: List[ScreenInfo] = []
        self._mics: List[str] = []
        self._sys_devs: List[str] = []
        self._elapsed = 0
        self._current_output = ''

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)

        self._build_ui()
        self._load_devices()
        self._check_ffmpeg()

    # ── Build UI ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel('🎬  Grabación de Pantalla')
        title.setStyleSheet('font-size: 18px; font-weight: bold; color: #89b4fa;')
        root.addWidget(title)
        root.addWidget(_sep())

        # ── Screen ────────────────────────────────────────────────
        root.addWidget(_section_lbl('PANTALLA'))
        self._screen_combo = QComboBox()
        root.addWidget(self._screen_combo)
        root.addWidget(_sep())

        # ── Audio ─────────────────────────────────────────────────
        root.addWidget(_section_lbl('AUDIO'))

        mic_row = QHBoxLayout()
        self._chk_mic = QCheckBox('Micrófono')
        self._chk_mic.setChecked(True)
        self._chk_mic.stateChanged.connect(
            lambda: self._mic_combo.setEnabled(self._chk_mic.isChecked()))
        mic_row.addWidget(self._chk_mic)
        self._mic_combo = QComboBox()
        self._mic_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        mic_row.addWidget(self._mic_combo)
        root.addLayout(mic_row)

        sys_row = QHBoxLayout()
        self._chk_sys = QCheckBox('Audio del sistema')
        self._chk_sys.setChecked(True)
        self._chk_sys.stateChanged.connect(
            lambda: self._sys_combo.setEnabled(self._chk_sys.isChecked()))
        sys_row.addWidget(self._chk_sys)
        self._sys_combo = QComboBox()
        self._sys_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sys_row.addWidget(self._sys_combo)
        root.addLayout(sys_row)
        root.addWidget(_sep())

        # ── Output folder (read-only, configured in Settings) ─────
        folder_row = QHBoxLayout()
        folder_row.addWidget(_section_lbl('GUARDAR EN:'))
        self._folder_lbl = QLabel(self._config.recordings_folder)
        self._folder_lbl.setStyleSheet('font-size: 12px; color: #a6adc8;')
        self._folder_lbl.setWordWrap(True)
        folder_row.addWidget(self._folder_lbl, 1)
        root.addLayout(folder_row)
        root.addWidget(_sep())

        # ── Timer display ─────────────────────────────────────────
        timer_box = QVBoxLayout()
        timer_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        timer_box.setSpacing(4)

        self._timer_lbl = QLabel('00:00:00')
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer_lbl.setStyleSheet(
            'font-size: 52px; font-weight: bold; color: #cdd6f4; font-family: monospace;')
        timer_box.addWidget(self._timer_lbl)

        self._status_lbl = QLabel('● EN ESPERA')
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_status('● EN ESPERA', '#6c7086', bold=False)
        timer_box.addWidget(self._status_lbl)
        root.addLayout(timer_box)

        # ── Control buttons ───────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(12)

        self._btn_start = QPushButton('▶  Iniciar grabación')
        self._btn_start.setObjectName('btn_start')
        self._btn_start.clicked.connect(self._on_start_clicked)
        btn_row.addWidget(self._btn_start)

        self._btn_pause = QPushButton('⏸  Pausar')
        self._btn_pause.setObjectName('btn_pause')
        self._btn_pause.clicked.connect(self._on_pause_clicked)
        self._btn_pause.hide()
        btn_row.addWidget(self._btn_pause)

        self._btn_resume = QPushButton('▶  Reanudar')
        self._btn_resume.setObjectName('btn_resume')
        self._btn_resume.clicked.connect(self._on_resume_clicked)
        self._btn_resume.hide()
        btn_row.addWidget(self._btn_resume)

        self._btn_stop = QPushButton('⏹  Detener')
        self._btn_stop.setObjectName('btn_stop')
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        self._btn_stop.hide()
        btn_row.addWidget(self._btn_stop)

        root.addLayout(btn_row)
        root.addWidget(_sep())

        # ── Transcription ─────────────────────────────────────────
        trans_hdr = QHBoxLayout()
        trans_hdr.addWidget(_section_lbl('TRANSCRIPCIÓN EN ESPAÑOL'))
        trans_hdr.addStretch()
        self._btn_copy = QPushButton('Copiar')
        self._btn_copy.setObjectName('btn_copy')
        self._btn_copy.clicked.connect(self._copy_transcription)
        self._btn_copy.hide()
        trans_hdr.addWidget(self._btn_copy)
        root.addLayout(trans_hdr)

        self._trans_edit = QTextEdit()
        self._trans_edit.setReadOnly(True)
        self._trans_edit.setMinimumHeight(130)
        self._trans_edit.setPlaceholderText(
            'La transcripción aparecerá aquí al finalizar la grabación…')
        root.addWidget(self._trans_edit, 1)

        root.addWidget(_sep())

        # ── Summary ───────────────────────────────────────────────
        sum_hdr = QHBoxLayout()
        sum_hdr.addWidget(_section_lbl('RESUMEN DE LA REUNIÓN'))
        sum_hdr.addStretch()
        self._btn_copy_sum = QPushButton('Copiar')
        self._btn_copy_sum.setObjectName('btn_copy')
        self._btn_copy_sum.clicked.connect(self._copy_summary)
        self._btn_copy_sum.hide()
        sum_hdr.addWidget(self._btn_copy_sum)
        root.addLayout(sum_hdr)

        self._sum_edit = QTextEdit()
        self._sum_edit.setReadOnly(True)
        self._sum_edit.setMinimumHeight(130)
        self._sum_edit.setPlaceholderText(
            'El resumen aparecerá aquí una vez completada la transcripción…')
        root.addWidget(self._sum_edit, 1)

    # ── Setup ─────────────────────────────────────────────────────

    def _load_devices(self):
        self._screens = get_screens()
        for s in self._screens:
            self._screen_combo.addItem(s.label(), s)

        self._mics, self._sys_devs = get_audio_devices()

        if self._mics:
            self._mic_combo.addItems(self._mics)
        else:
            self._chk_mic.setEnabled(False)
            self._mic_combo.setEnabled(False)
            self._mic_combo.addItem('No se detectaron micrófonos')

        if self._sys_devs:
            self._sys_combo.addItems(self._sys_devs)
        else:
            self._chk_sys.setEnabled(False)
            self._sys_combo.setEnabled(False)
            self._sys_combo.addItem('No se detectó audio del sistema')

    def _check_ffmpeg(self):
        if not ffmpeg_available():
            self._btn_start.setEnabled(False)
            self._btn_start.setText('FFmpeg no encontrado')
            self._set_status('⚠ Instala FFmpeg y agrégalo al PATH', '#f38ba8', bold=True)

    # ── Helpers ───────────────────────────────────────────────────

    def _set_status(self, text: str, color: str, bold: bool = True):
        weight = 'bold' if bold else 'normal'
        self._status_lbl.setStyleSheet(f'font-size: 13px; color: {color}; font-weight: {weight};')
        self._status_lbl.setText(text)

    def _set_controls(self, state: str):
        idle = state == 'idle'
        self._btn_start.setVisible(idle)
        self._btn_pause.setVisible(state == 'recording')
        self._btn_resume.setVisible(state == 'paused')
        self._btn_stop.setVisible(state in ('recording', 'paused'))

        self._screen_combo.setEnabled(idle)

        if idle:
            self._chk_mic.setEnabled(bool(self._mics))
            self._mic_combo.setEnabled(self._chk_mic.isChecked() and bool(self._mics))
            self._chk_sys.setEnabled(bool(self._sys_devs))
            self._sys_combo.setEnabled(self._chk_sys.isChecked() and bool(self._sys_devs))
        else:
            for w in (self._chk_mic, self._mic_combo, self._chk_sys, self._sys_combo):
                w.setEnabled(False)

    def _build_output_path(self) -> str:
        folder = self._config.recordings_folder or str(Path.home() / 'Videos' / 'goujana')
        os.makedirs(folder, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return os.path.join(folder, f'grabacion_{ts}.mp4')

    def _tick(self):
        self._elapsed += 1
        h, rem = divmod(self._elapsed, 3600)
        m, s = divmod(rem, 60)
        self._timer_lbl.setText(f'{h:02d}:{m:02d}:{s:02d}')

    # ── Button handlers ───────────────────────────────────────────

    def _on_start_clicked(self):
        screen: Optional[ScreenInfo] = self._screen_combo.currentData()
        if screen is None:
            return
        mic = self._mic_combo.currentText() if (self._chk_mic.isChecked() and self._mics) else None
        sys_audio = self._sys_combo.currentText() if (self._chk_sys.isChecked() and self._sys_devs) else None
        self._current_output = self._build_output_path()
        self._elapsed = 0
        self._timer_lbl.setText('00:00:00')
        self._trans_edit.clear()
        self._btn_copy.hide()
        self._recorder.start(screen, self._current_output, mic=mic, sys_audio=sys_audio)

    def _on_pause_clicked(self):
        self._btn_pause.setEnabled(False)
        self._tick_timer.stop()
        self._recorder.pause()

    def _on_resume_clicked(self):
        self._recorder.resume()

    def _on_stop_clicked(self):
        self._btn_stop.setEnabled(False)
        self._btn_pause.setEnabled(False)
        self._tick_timer.stop()
        self._recorder.stop()
        self._set_status('Procesando segmentos…', '#a6adc8', bold=False)

    # ── Recorder signals ──────────────────────────────────────────

    def _on_started(self):
        self._tick_timer.start(1000)
        self._set_controls('recording')
        self._btn_pause.setEnabled(True)
        self._btn_stop.setEnabled(True)
        self._set_status('● GRABANDO', '#f38ba8')

    def _on_paused(self):
        self._set_controls('paused')
        self._btn_stop.setEnabled(True)
        self._set_status('⏸ PAUSADO', '#fb923c')

    def _on_resumed(self):
        self._tick_timer.start(1000)
        self._set_controls('recording')
        self._btn_pause.setEnabled(True)
        self._btn_stop.setEnabled(True)
        self._set_status('● GRABANDO', '#f38ba8')

    def _on_finished(self, path: str):
        self._set_controls('idle')
        self._set_status(f'✓ Guardado: {os.path.basename(path)}', '#4ade80')
        self._trans_edit.clear()
        self._sum_edit.clear()
        self._btn_copy.hide()
        self._btn_copy_sum.hide()
        self._start_transcription(path)

    def _on_error(self, msg: str):
        self._tick_timer.stop()
        self._set_controls('idle')
        self._set_status(f'✗ {msg[:100]}', '#f38ba8')

    # ── Transcription ─────────────────────────────────────────────

    def _start_transcription(self, path: str):
        api_key = self._config.groq_api_key
        if not api_key:
            self._trans_edit.setPlaceholderText(
                '⚠ Configura tu API key de Groq en ⚙ Configuración para activar la transcripción.')
            return
        self._trans_edit.setPlaceholderText('Extrayendo audio…')
        self._transcriber = TranscriberThread(path, api_key, self)
        self._transcriber.progress.connect(self._trans_edit.setPlaceholderText)
        self._transcriber.done.connect(self._on_transcription_done)
        self._transcriber.error.connect(
            lambda e: self._trans_edit.setPlaceholderText(f'Error: {e}'))
        self._transcriber.start()

    def _on_transcription_done(self, text: str):
        self._trans_edit.setPlainText(text)
        self._btn_copy.show()
        txt_path = os.path.splitext(self._current_output)[0] + '_transcripcion.txt'
        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception:
            pass
        self._start_summary(text)

    def _copy_transcription(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._trans_edit.toPlainText())

    # ── Summary ───────────────────────────────────────────────────

    def _start_summary(self, transcription: str):
        self._sum_edit.setPlaceholderText('Generando resumen con IA…')
        self._summarizer = SummarizerThread(transcription, self._config.groq_api_key, self)
        self._summarizer.done.connect(self._on_summary_done)
        self._summarizer.error.connect(
            lambda e: self._sum_edit.setPlaceholderText(f'Error al resumir: {e}'))
        self._summarizer.start()

    def _on_summary_done(self, text: str):
        self._sum_edit.setPlainText(text)
        self._btn_copy_sum.show()
        sum_path = os.path.splitext(self._current_output)[0] + '_resumen.txt'
        try:
            with open(sum_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception:
            pass

    def _copy_summary(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._sum_edit.toPlainText())
