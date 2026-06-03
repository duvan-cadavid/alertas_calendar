import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QFrame, QSizePolicy, QScrollArea, QSlider,
    QApplication,
)

from core.mic_volume import get_mic_volume, set_mic_volume

from config.settings import Config
from core.recorder import ScreenRecorder, ScreenInfo, get_screens, get_audio_devices, ffmpeg_available, LOG_PATH
from core.transcriber import TranscriberThread
from core.summarizer import SummarizerThread


class ScreenThumbnailSelector(QWidget):
    """Clickable screenshot cards for selecting which screen to record.

    Shows a live screenshot of every connected monitor side by side.
    The user clicks the image that matches the screen they want to capture.
    Works at any resolution or DPI; uses a horizontal scroll for 3+ screens.
    """

    _TW = 240   # thumbnail width  (logical px)
    _TH = 135   # thumbnail height (16 : 9)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._screens:  List[ScreenInfo] = []
        self._cards:    list = []     # list of (QLabel thumb, bool has_pixmap)
        self._selected  = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(
            'QScrollArea { border:none; background:transparent; }'
            'QScrollBar:horizontal { background:#181825; height:6px; border-radius:3px; }'
            'QScrollBar::handle:horizontal { background:#45475a; border-radius:3px; min-width:20px; }'
            'QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }'
        )
        self._scroll.setFixedHeight(self._TH + 42)   # thumb + label + spacing

        self._inner = QWidget()
        self._row   = QHBoxLayout(self._inner)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(12)
        self._row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

    # ── Public ────────────────────────────────────────────────────

    def load(self, screens: List[ScreenInfo], selected_name: str = '') -> None:
        """(Re)populate cards with fresh screenshots and restore selection."""
        self._screens = screens
        self._cards.clear()

        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        qt_screens = QApplication.screens()
        for idx, info in enumerate(screens):
            self._row.addWidget(self._make_card(idx, info, qt_screens))

        sel = next((i for i, s in enumerate(screens) if s.name == selected_name), 0)
        self._apply(sel)

    def selected_screen(self) -> Optional[ScreenInfo]:
        if self._selected < len(self._screens):
            return self._screens[self._selected]
        return self._screens[0] if self._screens else None

    def selected_label(self) -> str:
        s = self.selected_screen()
        return f'Pantalla {self._selected + 1}  ({s.width}×{s.height})' if s else '—'

    # ── Internal ──────────────────────────────────────────────────

    def _make_card(self, idx: int, info: ScreenInfo, qt_screens: list) -> QWidget:
        card = QWidget()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(5)

        thumb = QLabel()
        thumb.setFixedSize(self._TW, self._TH)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        has_px = False
        if idx < len(qt_screens):
            px = qt_screens[idx].grabWindow(0)
            if not px.isNull():
                thumb.setPixmap(
                    px.scaled(self._TW - 4, self._TH - 4,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )
                has_px = True

        if not has_px:
            thumb.setText(f'🖥\nPantalla {idx + 1}')

        self._cards.append((thumb, has_px))
        vbox.addWidget(thumb)

        lbl = QLabel(f'Pantalla {idx + 1}  ·  {info.width}×{info.height}')
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet('font-size:11px; color:#6c7086; background:transparent; border:none;')
        vbox.addWidget(lbl)

        for w in (card, thumb, lbl):
            w.mousePressEvent = lambda _e, i=idx: self._apply(i)

        return card

    def _apply(self, idx: int) -> None:
        self._selected = idx
        for i, (thumb, has_px) in enumerate(self._cards):
            border = '3px solid #89b4fa' if i == idx else '2px solid #313244'
            base   = f'border:{border}; border-radius:6px; background:#1e1e2e;'
            thumb.setStyleSheet(base if has_px else base + ' color:#6c7086; font-size:13px;')


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
QSlider#vol_slider::groove:horizontal {
    height: 6px; background: #313244; border-radius: 3px;
}
QSlider#vol_slider::handle:horizontal {
    background: #89b4fa; border: none;
    width: 14px; height: 14px; border-radius: 7px; margin: -4px 0;
}
QSlider#vol_slider::sub-page:horizontal {
    background: #89b4fa; border-radius: 3px;
}
QSlider#vol_slider:disabled::sub-page:horizontal { background: #45475a; }
QSlider#vol_slider:disabled::handle:horizontal   { background: #45475a; }
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
        self._indicator      = None          # RecordingIndicator (shown while recording)
        self._border         = None          # RecordingBorderOverlay (pulsing screen border)
        self._rec_screen_geo = QRect()       # geometry of the screen being recorded
        self._results_win    = None          # RecordingResultsWindow

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

        # ── Mic volume (always visible) ───────────────────────────
        layout.addWidget(self._build_volume_row())
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

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(self._lbl('PANTALLA  —  haz clic en la imagen que ves', '11px', '#6c7086'))
        hdr_row.addStretch()
        btn_refresh = QPushButton('↻')
        btn_refresh.setObjectName('btn_config')
        btn_refresh.setFixedSize(26, 26)
        btn_refresh.setToolTip('Tomar nuevas capturas de pantalla')
        btn_refresh.clicked.connect(self._refresh_screenshots)
        hdr_row.addWidget(btn_refresh)
        layout.addLayout(hdr_row)

        self._screen_selector = ScreenThumbnailSelector()
        layout.addWidget(self._screen_selector)

        layout.addWidget(self._lbl('MICRÓFONO', '11px', '#6c7086'))
        mic_row = QHBoxLayout()
        self._chk_mic = QCheckBox('Activar micrófono')
        self._chk_mic.setChecked(True)
        self._chk_mic.stateChanged.connect(self._on_mic_chk_changed)
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
        self._screen_selector.load(self._screens, self._config.rec_screen_name)

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
            self._lbl_screen.setText(f'🖥  {self._screen_selector.selected_label()}')
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
            self._refresh_screenshots()

    def _refresh_screenshots(self):
        sel = self._screen_selector.selected_screen()
        self._screen_selector.load(
            self._screens,
            sel.name if sel else self._config.rec_screen_name,
        )

    def _build_volume_row(self) -> QWidget:
        """Always-visible mic OS volume control."""
        row = QWidget()
        row.setStyleSheet(
            'QWidget { background:#1e1e2e; border-radius:8px; border:1px solid #313244; }')
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        lbl = QLabel('🎙  Volumen del micrófono (sistema):')
        lbl.setStyleSheet('font-size: 12px; color: #a6adc8; border: none;')
        layout.addWidget(lbl)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setObjectName('vol_slider')
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(int(get_mic_volume() * 100))
        self._vol_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self._vol_slider)

        self._vol_pct = QLabel(f'{self._vol_slider.value()}%')
        self._vol_pct.setFixedWidth(36)
        self._vol_pct.setStyleSheet('font-size: 12px; color: #89b4fa; border: none;')
        layout.addWidget(self._vol_pct)

        self._vol_slider.valueChanged.connect(self._on_vol_changed)
        return row

    def _on_mic_chk_changed(self):
        self._mic_combo.setEnabled(self._chk_mic.isChecked())

    def _on_vol_changed(self, value: int):
        self._vol_pct.setText(f'{value}%')
        set_mic_volume(value / 100.0)

    def _save_device_config(self):
        screen = self._screen_selector.selected_screen()
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

        # Use the thumbnail the user clicked as the single source of truth.
        # This guarantees that the selected image, the recorded area, and the
        # red border all refer to the exact same physical screen.
        screen = self._screen_selector.selected_screen() or self._resolve_screen()
        if not screen:
            self._set_status('⚠  No se encontró la pantalla.', '#f38ba8')
            return

        mic = self._config.rec_mic_id or None
        sys_audio = self._config.rec_sys_id or None
        self._current_output = self._build_output_path()
        self._trans_text = ''
        self._sum_text   = ''
        self._trans_done = False
        self._sum_done   = False

        # Prefer index-based lookup (O(1), same session) then fall back to
        # name match in case screens were reconnected since _load_devices ran.
        qt_screens = QApplication.screens()
        if screen.index < len(qt_screens) and qt_screens[screen.index].name() == screen.name:
            qt_screen = qt_screens[screen.index]
        else:
            qt_screen = next(
                (s for s in qt_screens if s.name() == screen.name),
                QApplication.primaryScreen(),
            )
        self._rec_screen_geo = qt_screen.geometry()

        import logging
        _log = logging.getLogger('recorder')
        _log.info('=== Recording start ===')
        _log.info('User selected: index=%d, name=%r, label=%r',
                  screen.index, screen.name, screen.label())
        _log.info('Qt screen found: index=%s, name=%r, geometry=%s',
                  next((i for i, s in enumerate(qt_screens) if s is qt_screen), '?'),
                  qt_screen.name(), qt_screen.geometry())
        _log.info('Recording output: %s', self._current_output)

        self._recorder.start(screen, self._current_output, mic=mic, sys_audio=sys_audio)

    # ── Recorder signals ──────────────────────────────────────────

    def _on_rec_started(self):
        self.hide()
        self._show_indicator()

    def _on_rec_paused(self):
        if self._indicator:
            self._indicator.set_paused(True)
        if self._border:
            self._border.set_paused(True)

    def _on_rec_resumed(self):
        if self._indicator:
            self._indicator.set_paused(False)
        if self._border:
            self._border.set_paused(False)

    def _on_rec_finished(self, path: str):
        if self._indicator:
            self._indicator.close()
            self._indicator = None
        if self._border:
            self._border.close()
            self._border = None
        self._set_status('✓ Grabación guardada. Transcribiendo…', '#4ade80')
        self._start_transcription(path)

    def _on_rec_error(self, msg: str):
        if self._indicator:
            self._indicator.close()
            self._indicator = None
        if self._border:
            self._border.close()
            self._border = None
        self.show()
        self._set_status(f'✗ Error: {msg[:120]}', '#f38ba8')

    # ── Indicator ─────────────────────────────────────────────────

    def _show_indicator(self):
        from ui.recording_indicator import RecordingIndicator
        from ui.recording_border import RecordingBorderOverlay
        self._indicator = RecordingIndicator()
        self._indicator.pause_clicked.connect(self._on_indicator_pause)
        self._indicator.stop_clicked.connect(self._on_indicator_stop)
        self._indicator.show()

        geo = self._rec_screen_geo
        self._border = RecordingBorderOverlay(geo)
        self._border.show()
        # Reapply geometry after show() so Windows creates the native window
        # in the correct per-monitor DPI context (relevant for mixed-DPI setups).
        self._border.setGeometry(geo)
        self._indicator.raise_()   # keep the floating control above the border

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
        self._transcriber = TranscriberThread(path, self)
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
        self._summarizer = SummarizerThread(transcription, self)
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
