from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication,
)

from api.client import Appointment


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone().strftime('%I:%M %p').lstrip('0')


_STYLE = """
    QLabel#title {
        color: #89b4fa;
        font-size: 36px;
        font-weight: bold;
        letter-spacing: 3px;
    }
    QLabel#subtitle {
        color: #a6e3a1;
        font-size: 22px;
        font-weight: bold;
    }
    QLabel#event_name {
        color: #FFFFFF;
        font-size: 40px;
        font-weight: bold;
    }
    QLabel#time_label {
        color: #00D4FF;
        font-size: 26px;
        font-weight: bold;
    }
    QLabel#hint {
        color: #6c7086;
        font-size: 15px;
        font-style: italic;
    }

    QPushButton#btn_now {
        background-color: #1e3a5f; color: #89b4fa;
        border: 2px solid #89b4fa; border-radius: 12px;
        font-size: 20px; font-weight: bold;
        padding: 22px 56px; letter-spacing: 1px;
    }
    QPushButton#btn_now:hover   { background-color: #264a73; color: #cdd6f4; }
    QPushButton#btn_now:pressed { background-color: #0d2040; }

    QPushButton#btn_later {
        background-color: #2e2a06; color: #f9e2af;
        border: 2px solid #f9e2af; border-radius: 12px;
        font-size: 18px; font-weight: bold;
        padding: 22px 40px;
    }
    QPushButton#btn_later:hover   { background-color: #3e3a10; }
    QPushButton#btn_later:pressed { background-color: #1e1a00; }

    QPushButton#btn_cancel {
        background-color: transparent; color: #585b70;
        border: 1px solid #45475a; border-radius: 12px;
        font-size: 16px; font-weight: bold;
        padding: 22px 40px;
    }
    QPushButton#btn_cancel:hover   { background-color: #1e1e2e; color: #a6adc8; border-color: #6c7086; }
    QPushButton#btn_cancel:pressed { background-color: #11111b; }
"""


class RecordingPromptWindow(QWidget):
    """Full-screen prompt shown after attendance is confirmed.

    First appearance (show_cancel=False): two buttons — record now / in 5 min.
    Second appearance (show_cancel=True): adds a third Cancel button.
    """
    record_now   = pyqtSignal()
    record_later = pyqtSignal()
    dismissed    = pyqtSignal()

    def __init__(self, appointment: Appointment, show_cancel: bool = False):
        super().__init__()
        self.appointment = appointment
        self._show_cancel = show_cancel
        self._setup_window()
        self._setup_ui()

    # ── Window setup ──────────────────────────────────────────────

    def _setup_window(self):
        screens = QApplication.screens()
        if screens:
            geo = screens[0].geometry()
            for s in screens[1:]:
                geo = geo.united(s.geometry())
            self.setGeometry(geo)

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        try:
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        except AttributeError:
            pass

        self.setWindowFlags(flags)
        self.setStyleSheet(_STYLE)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0,  QColor(5, 15, 40))
        grad.setColorAt(0.45, QColor(10, 20, 55))
        grad.setColorAt(1.0,  QColor(5, 15, 40))
        painter.fillRect(self.rect(), QBrush(grad))

    def showEvent(self, event):
        super().showEvent(event)
        self.showFullScreen()
        self._force_raise()
        self._raise_timer = QTimer(self)
        self._raise_timer.timeout.connect(self._force_raise)
        self._raise_timer.start(300)
        QTimer.singleShot(3000, self._raise_timer.stop)

    def _force_raise(self):
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        pass  # block keyboard on fullscreen

    # ── UI ────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(100, 60, 100, 60)
        root.addStretch()

        center = QVBoxLayout()
        center.setSpacing(20)
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("🎬  GRABACIÓN DE SESIÓN")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(title)

        subtitle = QLabel("✓  Asistencia confirmada")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(subtitle)

        center.addWidget(self._sep())

        time_lbl = QLabel(
            f"⏰   {_fmt_time(self.appointment.start_date)}"
            f"  —  {_fmt_time(self.appointment.end_date)}"
        )
        time_lbl.setObjectName("time_label")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(time_lbl)

        name_lbl = QLabel(self.appointment.text.upper())
        name_lbl.setObjectName("event_name")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        center.addWidget(name_lbl)

        center.addSpacing(10)
        center.addWidget(self._sep())
        center.addSpacing(28)

        hint = QLabel("¿Deseas grabar esta sesión?")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(hint)

        center.addSpacing(8)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(24)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_now = QPushButton("▶   INICIAR GRABACIÓN AHORA")
        btn_now.setObjectName("btn_now")
        btn_now.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_now.setMinimumHeight(72)
        btn_now.clicked.connect(self._on_now)
        btn_row.addWidget(btn_now)

        btn_later = QPushButton("⏱   INICIAR EN 5 MINUTOS")
        btn_later.setObjectName("btn_later")
        btn_later.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_later.setMinimumHeight(72)
        btn_later.clicked.connect(self._on_later)
        btn_row.addWidget(btn_later)

        if self._show_cancel:
            btn_cancel = QPushButton("✗   CANCELAR")
            btn_cancel.setObjectName("btn_cancel")
            btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cancel.setMinimumHeight(72)
            btn_cancel.clicked.connect(self._on_cancel)
            btn_row.addWidget(btn_cancel)

        center.addLayout(btn_row)
        root.addLayout(center)
        root.addStretch()

    def _sep(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: rgba(255,255,255,0.12);")
        line.setFixedHeight(1)
        return line

    # ── Actions ───────────────────────────────────────────────────

    def _on_now(self):
        self.record_now.emit()
        self.close()

    def _on_later(self):
        self.record_later.emit()
        self.close()

    def _on_cancel(self):
        self.dismissed.emit()
        self.close()
