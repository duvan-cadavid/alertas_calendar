import math

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import QWidget

_BORDER_W = 5                          # logical pixels — DPI-aware on all screens
_COLOR    = QColor(243, 139, 168)      # #f38ba8 — same red as the recording indicator


class RecordingBorderOverlay(QWidget):
    """Full-screen transparent overlay with a slow pulsing red border.

    Accepts the exact QRect geometry of the recorded screen (in global
    logical-pixel coordinates) so the border always covers the right
    monitor regardless of index ordering or DPI configuration.
    All mouse/keyboard events pass through so the user can keep working.
    Hides automatically while paused and reappears on resume.
    """

    def __init__(self, screen_geo: QRect, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput   # Windows: clicks fall through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # cross-platform passthrough

        self._tick   = 0
        self._alpha  = 200
        self._paused = False

        self.setGeometry(screen_geo)

        # Pulse timer: 50 ms → 20 fps, smooth enough for a slow glow
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(50)

    # ── Animation ─────────────────────────────────────────────────

    def _pulse(self):
        self._tick += 1
        # Period = 2π / 0.157 ≈ 40 ticks × 50 ms ≈ 2 s per full cycle
        self._alpha = int(55 + 180 * (1.0 + math.sin(self._tick * 0.157)) / 2.0)
        self.update()

    # ── State ─────────────────────────────────────────────────────

    def set_paused(self, paused: bool):
        self._paused = paused
        if paused:
            self.hide()
        else:
            self.show()
            self.raise_()

    # ── Paint ─────────────────────────────────────────────────────

    def paintEvent(self, _):
        if self._paused:
            return
        p = QPainter(self)
        color = QColor(_COLOR)
        color.setAlpha(self._alpha)
        pen = QPen(color)
        pen.setWidth(_BORDER_W)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        half = _BORDER_W // 2
        p.drawRect(half, half,
                   self.width()  - _BORDER_W,
                   self.height() - _BORDER_W)