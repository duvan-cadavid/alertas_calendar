import math

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QApplication

_STYLE = """
QWidget#indicator {
    background-color: #11111b;
    border: 2px solid #f38ba8;
    border-radius: 12px;
}
QLabel#rec_dot  { color: #f38ba8; font-size: 13px; font-weight: bold; }
QLabel#rec_time { color: #cdd6f4; font-size: 13px; font-family: monospace; font-weight: bold; }
QPushButton#btn_stop {
    background-color: #f38ba8; color: #11111b;
    border: none; border-radius: 6px;
    font-size: 12px; font-weight: bold;
    padding: 4px 10px;
}
QPushButton#btn_stop:hover { background-color: #ff99b0; }
QPushButton#btn_pause {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    font-size: 12px; padding: 4px 10px;
}
QPushButton#btn_pause:hover { background-color: #45475a; }
"""

_BAR_HEIGHT = 8
_BAR_W      = 220


class _VuBar(QWidget):
    """Animated microphone level bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_BAR_W, _BAR_HEIGHT + 4)
        self._level = 0.0
        self._tick  = 0

    def next_tick(self):
        self._tick += 1
        # Simulate voice-like activity: base pulse + random ripple
        base   = 0.45 + 0.35 * abs(math.sin(self._tick * 0.18))
        ripple = 0.15 * abs(math.sin(self._tick * 0.73))
        self._level = min(1.0, base + ripple)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Background track
        p.setBrush(QBrush(QColor('#313244')))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 2, _BAR_W, _BAR_HEIGHT, 4, 4)
        # Filled level
        fill = int(_BAR_W * self._level)
        if fill > 0:
            # Gradient: green → yellow → red
            ratio = self._level
            if ratio < 0.6:
                r, g = int(ratio / 0.6 * 180), 220
            else:
                r, g = 220, int((1 - (ratio - 0.6) / 0.4) * 220)
            p.setBrush(QBrush(QColor(r, g, 60)))
            p.drawRoundedRect(0, 2, fill, _BAR_HEIGHT, 4, 4)


class RecordingIndicator(QWidget):
    """Small always-on-top floating window shown during screen recording."""
    pause_clicked = pyqtSignal()
    stop_clicked  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('indicator')
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(_STYLE)
        self.setFixedSize(300, 76)

        self._elapsed = 0
        self._paused  = False

        self._build_ui()
        self._position_top_right()

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(100)   # 10 fps — smooth bar + 1-s time updates

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget(self)
        container.setObjectName('indicator')
        container.setGeometry(0, 0, 300, 76)

        root = QVBoxLayout(container)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(4)

        # Row 1: dot + timer + buttons
        row = QHBoxLayout()
        row.setSpacing(8)

        self._dot = QLabel('● GRABANDO')
        self._dot.setObjectName('rec_dot')
        row.addWidget(self._dot)

        row.addStretch()

        self._time_lbl = QLabel('00:00:00')
        self._time_lbl.setObjectName('rec_time')
        row.addWidget(self._time_lbl)

        self._btn_pause = QPushButton('⏸')
        self._btn_pause.setObjectName('btn_pause')
        self._btn_pause.setFixedWidth(32)
        self._btn_pause.clicked.connect(self._on_pause)
        row.addWidget(self._btn_pause)

        btn_stop = QPushButton('⏹')
        btn_stop.setObjectName('btn_stop')
        btn_stop.setFixedWidth(32)
        btn_stop.clicked.connect(self.stop_clicked)
        row.addWidget(btn_stop)

        root.addLayout(row)

        # Row 2: VU bar
        self._vu = _VuBar(self)
        root.addWidget(self._vu, alignment=Qt.AlignmentFlag.AlignLeft)

    def _position_top_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 16, screen.top() + 16)

    # ── Slots ─────────────────────────────────────────────────────

    def _tick(self):
        self._vu.next_tick()
        # Update clock every 10 ticks (1 second)
        if self._elapsed % 10 == 0 and not self._paused:
            secs = self._elapsed // 10
            h, r = divmod(secs, 3600)
            m, s = divmod(r, 60)
            self._time_lbl.setText(f'{h:02d}:{m:02d}:{s:02d}')
        if not self._paused:
            self._elapsed += 1

    def _on_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._dot.setText('⏸ PAUSADO')
            self._dot.setStyleSheet('color: #fb923c; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('▶')
        else:
            self._dot.setText('● GRABANDO')
            self._dot.setStyleSheet('color: #f38ba8; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('⏸')
        self.pause_clicked.emit()

    def set_paused(self, paused: bool):
        """Sync UI state from external pause signal."""
        self._paused = paused
        if paused:
            self._dot.setText('⏸ PAUSADO')
            self._dot.setStyleSheet('color: #fb923c; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('▶')
        else:
            self._dot.setText('● GRABANDO')
            self._dot.setStyleSheet('color: #f38ba8; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('⏸')
