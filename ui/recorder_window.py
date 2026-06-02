import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QFrame, QSizePolicy, QScrollArea,
)

from config.settings import Config
from core.recorder import ScreenRecorder, ScreenInfo, get_screens, get_audio_devices, ffmpeg_available, LOG_PATH
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
QPushButton#btn_start {
    background-color: #1e3a5f; color: #89b4fa;
    border: 2px solid #89b4fa; border-radius: 12px;
    font-size: 22px; font-weight: bold;
    min-height: 80px; min-width: 280px;
}
QPushButton#btn_start:hover  { background-color: #264a73; }
QPushButton#btn_start:disabled { background-color: #181825; color: #45475a; border-color: #313244; }
QPushButton#btn_config {
    background-color: #1e1e2e; color: #89b4fa;
    border: 1px solid #313244; border-radius: 6px;
    padding: 6px 14px; font-size: 12px;
}
QPushButton#btn_config:hover { background-color: #313244; }
QPushButton#btn_save_config {
    background-color: #1e3a5f; color: #89b4fa;
    border: 1px solid #89b4fa; border-radius: 8px;
    padding: 8px 20px; font-weight: bold;
}
QPushButton#btn_save_config:hover { background-color: #264a73; }
QLabel#config_val {
    color: #a6adc8; font-size: 12px;
}
QLabel#config_val:hover { color: #cdd6f4; }
QFrame#sep { background-color: #313244; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #181825; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _sep():
    f = QFrame()
    f.setObjectName('sep')
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    return f


class RecorderWindow(QWidget):

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle('Grabación de Pantalla')
        self.setMinimumSize(600, 500)
        self.setStyleSheet(_STYLE)

        self._recorder   = ScreenRecorder(self)
        self._transcriber: Optional[TranscriberThread] = None
        self._summarizer:  Optional[SummarizerThread]  = None
        self._indicator  = None   # RecordingIndicator (shown while recording)
        self._results_win = None  # RecordingResultsWindow

        self._screens:   List[ScreenInfo] = []
        self._mics:      list = []
        self._sys_devs:  list = []
        self._current_output = ''
        self._trans_text = ''
        self._sum_text   = ''
        self._trans_done = False
        self._sum_done   = False

        self._recorder.recording_started.connect(self._on_rec_started)
        self._recorder.paused.connect(self._on_rec_paused)
        self._recorder.resumed.connect(self._on_rec_resumed)
        self._recorder.finished.connect(self._on_rec_finished)
        self._recorder.error.connect(self._on_rec_error)

        self._build_ui()
        self._load_devices()
        self._refresh_config_summary()
        self._check_ffmpeg()

    # ── Build UI ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(20)

        # ── Title ─────────────────────────────────────────────────
        title = QLabel('🎬  Grabación de Pantalla')
        title.setStyleSheet('font-size: 22px; font-weight: bold; color: #89b4fa;')
        layout.addWidget(title)
        layout.addWidget(_sep())

        # ── Config summary ────────────────────────────────────────
        cfg_hdr = QHBoxLayout()
        cfg_hdr.addWidget(self._lbl('CONFIGURACIÓN DE DISPOSITIVOS', '11px', '#6c7086'))
        cfg_hdr.addStretch()
        self._btn_change = QPushButton('✏  Cambiar')
        self._btn_change.setObjectName('btn_config')
        self._btn_change.clicked.connect(self._toggle_config_panel)
        cfg_hdr.addWidget(self._btn_change)
        layout.addLayout(cfg_hdr)

        # Summary labels (shown when config is saved)
        self._lbl_screen = self._config_val('🖥  —')
        self._lbl_mic    = self._config_val('🎙  —')
        self._lbl_sys    = self._config_val('🔊  —')
        self._lbl_folder = self._config_val('📁  —')
        self._summary_box = QWidget()
        sb = QVBoxLayout(self._summary_box)
        sb.setContentsMargins(12, 8, 12, 8)
        sb.setSpacing(4)
        self._summary_box.setStyleSheet(
            'QWidget { background:#1e1e2e; border-radius:8px; border:1px solid #313244; }')
        for lbl in (self._lbl_screen, self._lbl_mic, self._lbl_sys, self._lbl_folder):
            sb.addWidget(lbl)
        layout.addWidget(self._summary_box)

        # Config panel (hidden by default when config exists)
        self._config_panel = self._build_config_panel()
        layout.addWidget(self._config_panel)

        layout.addWidget(_sep())

        # ── Status label ──────────────────────────────────────────
        self._status_lbl = QLabel('')
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        layout.addWidget(self._status_lbl)

        # ── Start button ──────────────────────────────────────────
        btn_box = QHBoxLayout()
        btn_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._btn_start = QPushButton('▶  Iniciar grabación')
        self._btn_start.setObjectName('btn_start')
        self._btn_start.clicked.connect(self._on_start_clicked)
        btn_box.addWidget(self._btn_start)
        layout.addLayout(btn_box)

        # ── Diagnostics link ──────────────────────────────────────
        diag_row = QHBoxLayout()
        diag_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._btn_log = QPushButton('📋  Ver log de diagnóstico')
        self._btn_log.setObjectName('btn_config')
        self._btn_log.clicked.connect(self._open_log)
        diag_row.addWidget(self._btn_log)
        layout.addLayout(diag_row)

        layout.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

    def _build_config_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(
            'QWidget { background:#1e1e2e; border-radius:10px; border:1px solid #313244; }')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(self._lbl('PANTALLA', '11px', '#6c7086'))
        self._screen_combo = QComboBox()
        self._screen_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self._screen_combo)

        layout.addWidget(self._lbl('MICRÓFONO', '11px', '#6c7086'))
        mic_row = QHBoxLayout()
        self._chk_mic = QCheckBox('Activar micrófono')
        self._chk_mic.setChecked(True)
        self._chk_mic.stateChanged.connect(
            lambda: self._mic_combo.setEnabled(self._chk_mic.isChecked()))
        mic_row.addWidget(self._chk_mic)
        layout.addLayout(mic_row)
        self._mic_combo = QComboBox()
        self._mic_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._mic_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._mic_combo)

        layout.addWidget(self._lbl('AUDIO DEL SISTEMA', '11px', '#6c7086'))
        sys_row = QHBoxLayout()
        self._chk_sys = QCheckBox('Activar audio del sistema')
        self._chk_sys.setChecked(True)
        self._chk_sys.stateChanged.connect(
            lambda: self._sys_combo.setEnabled(self._chk_sys.isChecked()))
        sys_row.addWidget(self._chk_sys)
        layout.addLayout(sys_row)
        self._sys_combo = QComboBox()
        self._sys_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._sys_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._sys_combo)

        save_row = QHBoxLayout()
        save_row.addStretch()
        btn_save = QPushButton('✓  Guardar configuración')
        btn_save.setObjectName('btn_save_config')
        btn_save.clicked.connect(self._save_device_config)
        save_row.addWidget(btn_save)
        layout.addLayout(save_row)

        return panel

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _lbl(text: str, size: str = '13px', color: str = '#cdd6f4') -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(f'font-size: {size}; color: {color}; letter-spacing: 1px;')
        return l

    @staticmethod
    def _config_val(text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName('config_val')
        l.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        return l

    def _set_status(self, text: str, color: str = '#6c7086'):
        self._status_lbl.setStyleSheet(f'font-size: 12px; color: {color};')
        self._status_lbl.setText(text)

    # ── Device loading ────────────────────────────────────────────

    def _load_devices(self):
        self._screens = get_screens()
        self._screen_combo.clear()
        for s in self._screens:
            self._screen_combo.addItem(s.label(), s)

        self._mics, self._sys_devs = get_audio_devices()
        self._mic_combo.clear()
        self._sys_combo.clear()

        if self._mics:
            for device_id, display in self._mics:
                self._mic_combo.addItem(display, device_id)
        else:
            self._chk_mic.setEnabled(False)
            self._mic_combo.setEnabled(False)
            self._mic_combo.addItem('No se detectaron micrófonos')

        if self._sys_devs:
            for device_id, display in self._sys_devs:
                self._sys_combo.addItem(display, device_id)
        else:
            self._chk_sys.setEnabled(False)
            self._sys_combo.setEnabled(False)
            self._sys_combo.addItem('No se detectó audio del sistema')

        # Pre-select saved devices
        saved_screen = self._config.rec_screen_name
        for i in range(self._screen_combo.count()):
            s: ScreenInfo = self._screen_combo.itemData(i)
            if s and s.name == saved_screen:
                self._screen_combo.setCurrentIndex(i)
                break

        for combo, saved_id in [(self._mic_combo, self._config.rec_mic_id),
                                 (self._sys_combo, self._config.rec_sys_id)]:
            for i in range(combo.count()):
                if combo.itemData(i) == saved_id:
                    combo.setCurrentIndex(i)
                    break

    def _check_ffmpeg(self):
        if not ffmpeg_available():
            self._btn_start.setEnabled(False)
            self._btn_start.setText('FFmpeg no encontrado')
            self._set_status(
                '⚠  Instala FFmpeg y agrégalo al PATH del sistema', '#f38ba8')

    def _is_configured(self) -> bool:
        return bool(self._config.rec_screen_name)

    def _refresh_config_summary(self):
        if self._is_configured():
            self._config_panel.hide()
            self._summary_box.show()
            self._lbl_screen.setText(f'🖥  Pantalla: {self._config.rec_screen_name}')
            mic_label = self._mic_display(self._config.rec_mic_id) or 'Desactivado'
            sys_label = self._sys_display(self._config.rec_sys_id) or 'Desactivado'
            self._lbl_mic.setText(f'🎙  Micrófono: {mic_label}')
            self._lbl_sys.setText(f'🔊  Sistema: {sys_label}')
            self._lbl_folder.setText(f'📁  {self._config.recordings_folder}')
        else:
            self._summary_box.hide()
            self._config_panel.show()
            self._btn_change.hide()

    def _mic_display(self, device_id: str) -> str:
        if not device_id:
            return ''
        for did, label in self._mics:
            if did == device_id:
                return label.replace('🎙 ', '')
        return device_id

    def _sys_display(self, device_id: str) -> str:
        if not device_id:
            return ''
        for did, label in self._sys_devs:
            if did == device_id:
                return label.replace('🔊 ', '')
        return device_id

    def _toggle_config_panel(self):
        if self._config_panel.isVisible():
            self._config_panel.hide()
            self._summary_box.show()
        else:
            self._summary_box.hide()
            self._config_panel.show()

    def _save_device_config(self):
        screen: Optional[ScreenInfo] = self._screen_combo.currentData()
        if screen:
            self._config.rec_screen_name = screen.name
        self._config.rec_mic_id = (
            self._mic_combo.currentData()
            if self._chk_mic.isChecked() and self._mics else ''
        )
        self._config.rec_sys_id = (
            self._sys_combo.currentData()
            if self._chk_sys.isChecked() and self._sys_devs else ''
        )
        self._config.save()
        self._btn_change.show()
        self._refresh_config_summary()

    # ── Recording controls ────────────────────────────────────────

    def _resolve_screen(self) -> Optional[ScreenInfo]:
        """Find the saved screen by name in the current screen list."""
        name = self._config.rec_screen_name
        for s in self._screens:
            if s.name == name:
                return s
        return self._screens[0] if self._screens else None

    def _build_output_path(self) -> str:
        folder = self._config.recordings_folder or str(Path.home() / 'Videos' / 'goujana')
        os.makedirs(folder, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return os.path.join(folder, f'grabacion_{ts}.mp4')

    def _on_start_clicked(self):
        if not self._is_configured():
            self._set_status('⚠  Guarda la configuración de dispositivos primero.', '#fb923c')
            return

        screen = self._resolve_screen()
        if not screen:
            self._set_status('⚠  No se encontró la pantalla configurada.', '#f38ba8')
            return

        mic = self._config.rec_mic_id or None
        sys_audio = self._config.rec_sys_id or None
        self._current_output = self._build_output_path()
        self._trans_text = ''
        self._sum_text   = ''
        self._trans_done = False
        self._sum_done   = False

        self._recorder.start(screen, self._current_output, mic=mic, sys_audio=sys_audio)

    # ── Recorder signals ──────────────────────────────────────────

    def _on_rec_started(self):
        self.hide()
        self._show_indicator()

    def _on_rec_paused(self):
        if self._indicator:
            self._indicator.set_paused(True)

    def _on_rec_resumed(self):
        if self._indicator:
            self._indicator.set_paused(False)

    def _on_rec_finished(self, path: str):
        if self._indicator:
            self._indicator.close()
            self._indicator = None
        self._set_status('✓ Grabación guardada. Transcribiendo…', '#4ade80')
        self._start_transcription(path)

    def _on_rec_error(self, msg: str):
        if self._indicator:
            self._indicator.close()
            self._indicator = None
        self.show()
        self._set_status(f'✗ Error: {msg[:120]}', '#f38ba8')

    # ── Indicator ─────────────────────────────────────────────────

    def _show_indicator(self):
        from ui.recording_indicator import RecordingIndicator
        self._indicator = RecordingIndicator()
        self._indicator.pause_clicked.connect(self._on_indicator_pause)
        self._indicator.stop_clicked.connect(self._on_indicator_stop)
        self._indicator.show()

    def _on_indicator_pause(self):
        if self._recorder.state == 'recording':
            self._recorder.pause()
        else:
            self._recorder.resume()

    def _on_indicator_stop(self):
        if self._indicator:
            self._indicator._clock.stop()
        self._recorder.stop()

    # ── Transcription & Summary ───────────────────────────────────

    def _start_transcription(self, path: str):
        api_key = self._config.groq_api_key
        if not api_key:
            self._trans_done = True
            self._trans_text = '(Sin API key de Groq — transcripción no disponible)'
            self._check_open_results()
            return
        self._transcriber = TranscriberThread(path, api_key, self)
        self._transcriber.done.connect(self._on_trans_done)
        self._transcriber.error.connect(self._on_trans_error)
        self._transcriber.start()

    def _on_trans_done(self, text: str):
        self._trans_text = text
        self._trans_done = True
        txt_path = os.path.splitext(self._current_output)[0] + '_transcripcion.txt'
        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception:
            pass
        self._start_summary(text)
        self._check_open_results()

    def _on_trans_error(self, msg: str):
        self._trans_text = f'Error en transcripción:\n{msg}'
        self._trans_done = True
        self._check_open_results()

    def _start_summary(self, transcription: str):
        api_key = self._config.groq_api_key
        if not api_key:
            self._sum_done = True
            self._sum_text = '(Sin API key de Groq — resumen no disponible)'
            self._check_open_results()
            return
        self._summarizer = SummarizerThread(transcription, api_key, self)
        self._summarizer.done.connect(self._on_sum_done)
        self._summarizer.error.connect(self._on_sum_error)
        self._summarizer.start()

    def _on_sum_done(self, text: str):
        self._sum_text = text
        self._sum_done = True
        sum_path = os.path.splitext(self._current_output)[0] + '_resumen.txt'
        try:
            with open(sum_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception:
            pass
        # If results window is already open, update it live
        if self._results_win and self._results_win.isVisible():
            self._results_win.update_summary(text)
        else:
            self._check_open_results()

    def _on_sum_error(self, msg: str):
        self._sum_text = f'Error al generar resumen:\n{msg}'
        self._sum_done = True
        if self._results_win and self._results_win.isVisible():
            self._results_win.update_summary(self._sum_text)
        else:
            self._check_open_results()

    def _check_open_results(self):
        """Open results window as soon as transcription is ready (don't wait for summary)."""
        if not self._trans_done:
            return
        if self._results_win and self._results_win.isVisible():
            return
        from ui.recording_results import RecordingResultsWindow
        self._results_win = RecordingResultsWindow(
            self._current_output,
            self._trans_text,
            self._sum_text or 'Generando resumen…',
        )
        self._results_win.show()

    def _open_log(self):
        import subprocess as _sp
        if not LOG_PATH.exists():
            self._set_status(f'Log aún no existe: {LOG_PATH}', '#fb923c')
            return
        if sys.platform == 'win32':
            _sp.Popen(['explorer', '/select,', str(LOG_PATH)])
        else:
            _sp.Popen(['xdg-open', str(LOG_PATH.parent)])
