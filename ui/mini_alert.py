from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QBrush
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication

from api.client import Appointment

_STYLE = """
    QLabel#mini_title {
        color: #FFD700; font-size: 12px; font-weight: bold; letter-spacing: 2px;
    }
    QLabel#mini_event { color: #FFFFFF; font-size: 15px; font-weight: bold; }
    QLabel#mini_time  { color: #00D4FF; font-size: 13px; }
    QLabel#mini_info  { color: #CCCCCC; font-size: 12px; }
    QPushButton#mini_close {
        background: transparent; color: #888888; border: none; font-size: 16px; padding: 0px;
    }
    QPushButton#mini_close:hover { color: #FFFFFF; }
    QPushButton#mini_confirm {
        background-color: #00C853; color: #FFFFFF;
        border: none; border-radius: 6px;
        font-size: 12px; font-weight: bold; padding: 5px 12px;
    }
    QPushButton#mini_confirm:hover   { background-color: #69F0AE; color: #003300; }
    QPushButton#mini_confirm:pressed { background-color: #00701A; }
    QPushButton#mini_confirmed {
        background-color: #1b5e20; color: #a5d6a7;
        border: none; border-radius: 6px;
        font-size: 12px; padding: 5px 12px;
    }
"""

def _fmt(dt) -> str:
    return dt.astimezone().strftime('%I:%M %p').lstrip('0')


class MiniAlert(QWidget):
    confirmed = pyqtSignal(object)   # Appointment

    WIDTH  = 320
    HEIGHT = 155
    MARGIN = 16
    ANIM_MS = 350

    def __init__(self, appointment: Appointment, minutes_left: int):
        super().__init__()
        self._appointment = appointment
        self._setup_window()
        self._build_ui(minutes_left)
        self._animate_in()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setStyleSheet(_STYLE)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.WIDTH - self.MARGIN,
            screen.bottom() - self.HEIGHT - self.MARGIN,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.HEIGHT)
        grad.setColorAt(0, QColor(20, 25, 55, 235))
        grad.setColorAt(1, QColor(10, 15, 40, 235))
        painter.setBrush(QBrush(grad))
        painter.setPen(QColor(255, 165, 0, 180))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)

    def _build_ui(self, minutes_left: int):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 12, 12)
        root.setSpacing(4)

        # Título + cerrar
        top = QHBoxLayout()
        title = QLabel(f"⏰  EVENTO EN {minutes_left} MINUTO{'S' if minutes_left != 1 else ''}")
        title.setObjectName('mini_title')
        top.addWidget(title)
        top.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName('mini_close')
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self._animate_out)
        top.addWidget(close_btn)
        root.addLayout(top)

        _sel = lambda l: (l.setTextInteractionFlags(  # noqa: E731
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard), l)[1]

        event_lbl = _sel(QLabel(self._appointment.text))
        event_lbl.setObjectName('mini_event')
        event_lbl.setWordWrap(True)
        root.addWidget(event_lbl)

        time_lbl = _sel(QLabel(f"🕐  {_fmt(self._appointment.start_date)}  —  {_fmt(self._appointment.end_date)}"))
        time_lbl.setObjectName('mini_time')
        root.addWidget(time_lbl)

        if self._appointment.customer_name:
            info = _sel(QLabel(f"👤  {self._appointment.customer_name}"))
            info.setObjectName('mini_info')
            root.addWidget(info)

        # Botón confirmar asistencia
        self._confirm_btn = QPushButton("✓  Confirmar asistencia")
        self._confirm_btn.setObjectName('mini_confirm')
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_btn.clicked.connect(self._on_confirm)
        if self._appointment.assisted:
            self._mark_confirmed()
        root.addWidget(self._confirm_btn)

    def _on_confirm(self):
        self._mark_confirmed()
        self.confirmed.emit(self._appointment)
        QTimer.singleShot(1500, self._animate_out)

    def _mark_confirmed(self):
        self._confirm_btn.setText("✓  Asistencia confirmada")
        self._confirm_btn.setObjectName('mini_confirmed')
        self._confirm_btn.setStyleSheet(_STYLE)
        self._confirm_btn.setEnabled(False)

    def _animate_in(self):
        self.show()
        screen = QApplication.primaryScreen().availableGeometry()
        self._anim = QPropertyAnimation(self, b'pos')
        self._anim.setDuration(self.ANIM_MS)
        self._anim.setStartValue(QPoint(self.x(), screen.bottom()))
        self._anim.setEndValue(QPoint(self.x(), screen.bottom() - self.HEIGHT - self.MARGIN))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _animate_out(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self._anim_out = QPropertyAnimation(self, b'pos')
        self._anim_out.setDuration(self.ANIM_MS)
        self._anim_out.setStartValue(self.pos())
        self._anim_out.setEndValue(QPoint(self.x(), screen.bottom()))
        self._anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim_out.finished.connect(self.close)
        self._anim_out.start()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._animate_out()
