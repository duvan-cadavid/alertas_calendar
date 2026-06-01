from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication, QTextEdit,
)


from api.client import Appointment


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone().strftime('%I:%M %p').lstrip('0')


def _now_str() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M')


SNOOZE_MINUTES = 5

_MAIN_STYLE = """
    QLabel#badge {
        color: #FFD700;
        font-size: 20px;
        font-weight: bold;
        letter-spacing: 5px;
    }
    QLabel#event_name {
        color: #FFFFFF;
        font-size: 44px;
        font-weight: bold;
    }
    QLabel#time_label {
        color: #00D4FF;
        font-size: 30px;
        font-weight: bold;
    }
    QLabel#info { color: #DDDDDD; font-size: 19px; }
    QLabel#obs  { color: #AAAAAA; font-size: 16px; font-style: italic; }

    QPushButton#confirm {
        background-color: #00C853; color: #FFFFFF;
        border: none; border-radius: 10px;
        font-size: 18px; font-weight: bold;
        padding: 18px 48px; letter-spacing: 1px;
    }
    QPushButton#confirm:hover   { background-color: #69F0AE; color: #003300; }
    QPushButton#confirm:pressed { background-color: #00701A; }

    QPushButton#snooze {
        background-color: #E65100; color: #FFFFFF;
        border: none; border-radius: 10px;
        font-size: 16px; font-weight: bold; padding: 18px 36px;
    }
    QPushButton#snooze:hover   { background-color: #FF6D00; }
    QPushButton#snooze:pressed { background-color: #BF360C; }

    QPushButton#cancel_task {
        background-color: #B71C1C; color: #FFFFFF;
        border: none; border-radius: 10px;
        font-size: 16px; font-weight: bold; padding: 18px 36px;
    }
    QPushButton#cancel_task:hover   { background-color: #E53935; }
    QPushButton#cancel_task:pressed { background-color: #7F0000; }
"""

_OVERLAY_STYLE = """
    QWidget#overlay_panel {
        background-color: #1a1a2e;
        border: 2px solid #f38ba8;
        border-radius: 16px;
    }
    QLabel#ov_title {
        color: #f38ba8;
        font-size: 20px;
        font-weight: bold;
    }
    QLabel#ov_text {
        color: #cdd6f4;
        font-size: 15px;
    }
    QTextEdit#ov_input {
        background-color: #313244;
        color: #cdd6f4;
        border: 2px solid #45475a;
        border-radius: 8px;
        font-size: 15px;
        padding: 10px;
    }
    QTextEdit#ov_input:focus { border-color: #f38ba8; }
    QLabel#ov_error {
        color: #f38ba8;
        font-size: 13px;
    }
    QPushButton#ov_confirm {
        background-color: #B71C1C; color: #FFFFFF;
        border: none; border-radius: 8px;
        font-size: 15px; font-weight: bold; padding: 14px 32px;
    }
    QPushButton#ov_confirm:hover   { background-color: #E53935; }
    QPushButton#ov_confirm:pressed { background-color: #7F0000; }
    QPushButton#ov_back {
        background-color: #313244; color: #cdd6f4;
        border: 1px solid #45475a; border-radius: 8px;
        font-size: 15px; padding: 14px 32px;
    }
    QPushButton#ov_back:hover { background-color: #45475a; }
"""


class _CancelOverlay(QWidget):
    """Panel superpuesto dentro de AlertWindow — sin ventana separada."""

    confirmed = pyqtSignal(str)   # emite la justificación
    rejected  = pyqtSignal()

    def __init__(self, appointment: Appointment, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0,0,0,180);")
        self._appt = appointment
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        panel = QWidget()
        panel.setObjectName("overlay_panel")
        panel.setStyleSheet(_OVERLAY_STYLE)
        panel.setFixedWidth(560)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(16)

        title = QLabel("✗   Cancelar tarea")
        title.setObjectName("ov_title")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: rgba(243,139,168,0.3);")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        event_lbl = QLabel(f"Evento:  <b>{self._appt.text}</b>")
        event_lbl.setObjectName("ov_text")
        event_lbl.setWordWrap(True)
        layout.addWidget(event_lbl)

        reason_lbl = QLabel("Justifica la cancelación del evento:")
        reason_lbl.setObjectName("ov_text")
        layout.addWidget(reason_lbl)

        self._input = QTextEdit()
        self._input.setObjectName("ov_input")
        self._input.setPlaceholderText("Escribe el motivo de la cancelación...")
        self._input.setFixedHeight(110)
        layout.addWidget(self._input)

        self._error = QLabel("")
        self._error.setObjectName("ov_error")
        self._error.hide()
        layout.addWidget(self._error)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        back_btn = QPushButton("← Volver")
        back_btn.setObjectName("ov_back")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._on_back)
        btn_row.addWidget(back_btn)

        btn_row.addStretch()

        ok_btn = QPushButton("✗   Confirmar cancelación")
        ok_btn.setObjectName("ov_confirm")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)
        outer.addWidget(panel)

    def showEvent(self, event):
        super().showEvent(event)
        self.resize(self.parent().size())
        self._input.clear()
        self._error.hide()
        self._input.setFocus()

    def _on_back(self):
        self.rejected.emit()
        self.hide()

    def _on_confirm(self):
        text = self._input.toPlainText().strip()
        if not text:
            self._error.setText("⚠  Debes escribir una justificación para continuar.")
            self._error.show()
            return
        self.confirmed.emit(text)
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_back()
        else:
            super().keyPressEvent(event)


class AlertWindow(QWidget):
    confirmed = pyqtSignal(object)         # Appointment
    snoozed   = pyqtSignal(object, int)   # (Appointment, minutes)
    cancelled = pyqtSignal(object, str)   # (Appointment, new_observations)

    def __init__(self, appointment: Appointment):
        super().__init__()
        self.appointment = appointment
        self._setup_window()
        self._setup_ui()
        # El overlay se crea sobre el mismo widget — siempre visible
        self._overlay = _CancelOverlay(appointment, self)
        self._overlay.confirmed.connect(self._on_cancel_confirmed)
        self._overlay.rejected.connect(lambda: None)
        self._overlay.hide()

    # ── Ventana ───────────────────────────────────────────────────
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
        self.setStyleSheet(_MAIN_STYLE)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0,  QColor(8, 12, 35))
        grad.setColorAt(0.45, QColor(15, 25, 65))
        grad.setColorAt(1.0,  QColor(8, 12, 35))
        painter.fillRect(self.rect(), QBrush(grad))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_overlay'):
            self._overlay.resize(self.size())

    def showEvent(self, event):
        super().showEvent(event)
        self.showFullScreen()
        self._force_raise()
        # Repetir raise durante 3 segundos para ganar foco aunque haya otras ventanas abiertas
        self._raise_timer = QTimer(self)
        self._raise_timer.timeout.connect(self._force_raise)
        self._raise_timer.start(300)
        QTimer.singleShot(3000, self._raise_timer.stop)

    def _force_raise(self):
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        pass  # bloquear teclado en la ventana principal

    # ── UI ────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(100, 50, 100, 50)

        root.addStretch()
        center = QVBoxLayout()
        center.setSpacing(18)
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)

        badge = QLabel("🔔   EVENTO INICIANDO AHORA")
        badge.setObjectName("badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(badge)

        center.addWidget(self._sep())

        time_lbl = self._selectable(QLabel(
            f"⏰   {_fmt_time(self.appointment.start_date)}  —  {_fmt_time(self.appointment.end_date)}"
        ))
        time_lbl.setObjectName("time_label")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(time_lbl)

        name_lbl = self._selectable(QLabel(self.appointment.text.upper()))
        name_lbl.setObjectName("event_name")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        center.addWidget(name_lbl)

        center.addSpacing(6)

        if self.appointment.customer_name:
            lbl = self._selectable(QLabel(f"👤   Paciente / Cliente:  {self.appointment.customer_name}"))
            lbl.setObjectName("info")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            center.addWidget(lbl)

        if self.appointment.service_name:
            lbl = self._selectable(QLabel(f"⚕   Servicio:  {self.appointment.service_name}"))
            lbl.setObjectName("info")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            center.addWidget(lbl)

        if self.appointment.observations:
            lbl = self._selectable(QLabel("📝   Observaciones:"))
            lbl.setObjectName("info")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            center.addWidget(lbl)

            obs = self._selectable(QLabel(self.appointment.observations[:400]))
            obs.setObjectName("obs")
            obs.setAlignment(Qt.AlignmentFlag.AlignCenter)
            obs.setWordWrap(True)
            obs.setMaximumWidth(1000)
            center.addWidget(obs)

        center.addSpacing(8)
        center.addWidget(self._sep())
        center.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)
        btn_row.addStretch()

        snooze_btn = QPushButton(f"⏸   POSPONER {SNOOZE_MINUTES} MINUTOS")
        snooze_btn.setObjectName("snooze")
        snooze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        snooze_btn.setMinimumHeight(64)
        snooze_btn.clicked.connect(self._on_snooze)
        btn_row.addWidget(snooze_btn)

        cancel_btn = QPushButton("✗   CANCELAR TAREA")
        cancel_btn.setObjectName("cancel_task")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setMinimumHeight(64)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn)

        confirm_btn = QPushButton("✓   CONFIRMAR QUE ESTOY ATENDIENDO")
        confirm_btn.setObjectName("confirm")
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setMinimumHeight(64)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn)

        btn_row.addStretch()
        center.addLayout(btn_row)

        root.addLayout(center)
        root.addStretch()

    @staticmethod
    def _selectable(lbl: QLabel) -> QLabel:
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        lbl.setCursor(Qt.CursorShape.IBeamCursor)
        return lbl

    def _sep(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: rgba(255,255,255,0.15);")
        line.setFixedHeight(1)
        return line

    # ── Acciones ──────────────────────────────────────────────────
    def _on_confirm(self):
        self.confirmed.emit(self.appointment)
        self.close()

    def _on_snooze(self):
        self.snoozed.emit(self.appointment, SNOOZE_MINUTES)
        self.close()

    def _on_cancel(self):
        self._overlay.resize(self.size())
        self._overlay.show()
        self._overlay.raise_()

    def _on_cancel_confirmed(self, justification: str):
        existing  = (self.appointment.observations or '').strip()
        new_entry = f"[{_now_str()}] EVENTO CANCELADO — {justification}"
        new_obs   = f"{existing}\n{new_entry}".strip() if existing else new_entry
        self.cancelled.emit(self.appointment, new_obs)
        self.close()
