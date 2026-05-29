from datetime import datetime, date, timedelta
from typing import List

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGridLayout, QFrame, QSizePolicy,
)

from api.client import Appointment, SofisisClient
from config.settings import Config
from core.updater import UpdateChecker
from core.version import __version__

_MONTHS = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
           'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
_DAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

_STYLE = """
QWidget {
    background-color: #11111b;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Ubuntu', Arial, sans-serif;
}
QLabel#header_date { font-size: 22px; font-weight: bold; color: #89b4fa; }
QLabel#header_name { font-size: 14px; color: #6c7086; }
QLabel#loading     { font-size: 18px; color: #6c7086; }
QPushButton#refresh_btn {
    background-color: #1e1e2e; color: #89b4fa;
    border: 1px solid #313244; border-radius: 8px;
    padding: 8px 20px; font-size: 13px;
}
QPushButton#refresh_btn:hover { background-color: #313244; }
QPushButton#update_btn {
    background-color: #1e1e2e; color: #6c7086;
    border: 1px solid #313244; border-radius: 8px;
    padding: 8px 20px; font-size: 13px;
}
QPushButton#update_btn:hover:enabled { background-color: #313244; }
QPushButton#update_btn:disabled { color: #45475a; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""

_CARD_STYLES = {
    'past': """
        QFrame#card { background-color: #18181f; border: 1px solid #2a2a3a; border-radius: 12px; }
        QLabel#card_time  { color: #45475a; font-size: 12px; font-weight: bold; }
        QLabel#card_title { color: #585b70; font-size: 15px; font-weight: bold; }
        QLabel#card_info  { color: #45475a; font-size: 12px; }
        QLabel#card_badge { color: #45475a; font-size: 11px; }
        QPushButton#card_confirm { background-color: #1b5e20; color: #4caf50;
            border: 1px solid #2e7d32; border-radius: 6px; font-size: 11px; padding: 4px 10px; }
    """,
    'current': """
        QFrame#card { background-color: #0a2e1a; border: 2px solid #4ade80; border-radius: 12px; }
        QLabel#card_time  { color: #4ade80; font-size: 12px; font-weight: bold; }
        QLabel#card_title { color: #86efac; font-size: 15px; font-weight: bold; }
        QLabel#card_info  { color: #bbf7d0; font-size: 12px; }
        QLabel#card_badge { background-color: #4ade80; color: #052e16;
                            border-radius: 6px; padding: 2px 8px; font-size: 10px; font-weight: bold; }
        QPushButton#card_confirm { background-color: #00C853; color: #fff;
            border: none; border-radius: 6px; font-size: 11px; font-weight: bold; padding: 5px 12px; }
        QPushButton#card_confirm:hover { background-color: #69F0AE; color: #003300; }
        QPushButton#card_confirmed { background-color: #1b5e20; color: #a5d6a7;
            border: none; border-radius: 6px; font-size: 11px; padding: 5px 12px; }
    """,
    'soon': """
        QFrame#card { background-color: #2e1a06; border: 2px solid #fb923c; border-radius: 12px; }
        QLabel#card_time  { color: #fb923c; font-size: 12px; font-weight: bold; }
        QLabel#card_title { color: #fdba74; font-size: 15px; font-weight: bold; }
        QLabel#card_info  { color: #fed7aa; font-size: 12px; }
        QLabel#card_badge { background-color: #fb923c; color: #431407;
                            border-radius: 6px; padding: 2px 8px; font-size: 10px; font-weight: bold; }
        QPushButton#card_confirm { background-color: #00C853; color: #fff;
            border: none; border-radius: 6px; font-size: 11px; font-weight: bold; padding: 5px 12px; }
        QPushButton#card_confirm:hover { background-color: #69F0AE; color: #003300; }
        QPushButton#card_confirmed { background-color: #1b5e20; color: #a5d6a7;
            border: none; border-radius: 6px; font-size: 11px; padding: 5px 12px; }
    """,
    'future': """
        QFrame#card { background-color: #1e1e2e; border: 1px solid #313244; border-radius: 12px; }
        QLabel#card_time  { color: #89b4fa; font-size: 12px; font-weight: bold; }
        QLabel#card_title { color: #cdd6f4; font-size: 15px; font-weight: bold; }
        QLabel#card_info  { color: #a6adc8; font-size: 12px; }
        QLabel#card_badge { color: #6c7086; font-size: 11px; }
        QPushButton#card_confirm { background-color: #313244; color: #89b4fa;
            border: 1px solid #45475a; border-radius: 6px; font-size: 11px; padding: 4px 10px; }
        QPushButton#card_confirm:hover { background-color: #45475a; }
        QPushButton#card_confirmed { background-color: #1b5e20; color: #a5d6a7;
            border: none; border-radius: 6px; font-size: 11px; padding: 4px 10px; }
    """,
}


def _status(appt: Appointment) -> str:
    now = datetime.now().astimezone()
    if appt.end_date < now:
        return 'past'
    if appt.start_date <= now:
        return 'current'
    if appt.start_date - now <= timedelta(minutes=30):
        return 'soon'
    return 'future'


def _fmt(dt: datetime) -> str:
    return dt.astimezone().strftime('%I:%M %p').lstrip('0')


def _badge_text(status: str) -> str:
    return {'current': '● EN CURSO', 'soon': '⏰ PRONTO', 'past': 'Finalizado', 'future': ''}.get(status, '')


class _FetchThread(QThread):
    done = pyqtSignal(list)
    fail = pyqtSignal(str)

    def __init__(self, client: SofisisClient, user_id: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._user_id = user_id

    def run(self):
        try:
            self.done.emit(self._client.get_today_appointments(self._user_id))
        except Exception as e:
            self.fail.emit(str(e))


class AppointmentCard(QFrame):
    confirm_requested = pyqtSignal(int)   # appointment id

    def __init__(self, appt: Appointment):
        super().__init__()
        self.setObjectName('card')
        self._appt = appt
        status = _status(appt)
        self.setStyleSheet(_CARD_STYLES[status])
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._confirm_btn = None
        self._build(appt, status)

    def _build(self, appt: Appointment, status: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        # Hora + badge
        top = QHBoxLayout()
        time_lbl = QLabel(f"⏰ {_fmt(appt.start_date)}  —  {_fmt(appt.end_date)}")
        time_lbl.setObjectName('card_time')
        top.addWidget(time_lbl)
        top.addStretch()
        badge_text = _badge_text(status)
        if badge_text:
            badge = QLabel(badge_text)
            badge.setObjectName('card_badge')
            top.addWidget(badge)
        layout.addLayout(top)

        # Título
        title = QLabel(appt.text)
        title.setObjectName('card_title')
        title.setWordWrap(True)
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('background-color: rgba(255,255,255,0.08);')
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Info
        if appt.customer_name:
            info = QLabel(f"👤  {appt.customer_name}")
            info.setObjectName('card_info')
            layout.addWidget(info)

        if appt.service_name:
            svc = QLabel(f"⚕  {appt.service_name}")
            svc.setObjectName('card_info')
            layout.addWidget(svc)

        if appt.observations:
            obs = QLabel(f"📝  {appt.observations[:120]}{'…' if len(appt.observations) > 120 else ''}")
            obs.setObjectName('card_info')
            obs.setWordWrap(True)
            layout.addWidget(obs)

        # Botón confirmar asistencia
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._confirm_btn = QPushButton()
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if appt.assisted:
            self._set_confirmed()
        else:
            self._confirm_btn.setText("✓  Confirmar asistencia")
            self._confirm_btn.setObjectName('card_confirm')
            self._confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self._confirm_btn)
        layout.addLayout(btn_row)

    def _on_confirm(self):
        self._set_confirmed()
        self.confirm_requested.emit(self._appt.id)

    def _set_confirmed(self):
        self._confirm_btn.setText("✓  Asistencia confirmada")
        self._confirm_btn.setObjectName('card_confirmed')
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setStyleSheet(self.styleSheet())


class DashboardWindow(QWidget):
    COLS = 3
    REFRESH_MS = 60_000

    def __init__(self, config: Config):
        super().__init__()
        self._config = config
        self._client = SofisisClient(config.server_url, config.api_token)
        self._thread: _FetchThread | None = None
        self._update_checker: UpdateChecker | None = None
        self._update_url: str = ""
        self._update_btn: QPushButton | None = None

        self.setWindowTitle("Agenda de Hoy — Alertas de Calendarios")
        self.setMinimumSize(860, 600)
        self.resize(1000, 680)
        self.setStyleSheet(_STYLE)
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load)
        self._timer.start(self.REFRESH_MS)
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        left = QVBoxLayout()
        today = date.today()
        date_lbl = QLabel(f"📅  {_DAYS[today.weekday()]}  {today.day} de {_MONTHS[today.month]} {today.year}")
        date_lbl.setObjectName('header_date')
        left.addWidget(date_lbl)

        self._subtitle = QLabel("Cargando agenda…")
        self._subtitle.setObjectName('header_name')
        left.addWidget(self._subtitle)

        header.addLayout(left)
        header.addStretch()

        self._update_btn = QPushButton(f"⬆  Buscar actualizaciones  v{__version__}")
        self._update_btn.setObjectName('update_btn')
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.clicked.connect(self._check_for_updates)
        header.addWidget(self._update_btn)

        refresh = QPushButton("↻  Actualizar")
        refresh.setObjectName('refresh_btn')
        refresh.clicked.connect(self._load)
        header.addWidget(refresh)
        root.addLayout(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('background-color: #313244;')
        sep.setFixedHeight(1)
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(14)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._grid_container)
        root.addWidget(scroll)

        self._footer = QLabel("Actualización automática cada minuto")
        self._footer.setStyleSheet("color: #45475a; font-size: 11px;")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(self._footer)

    def _check_for_updates(self) -> None:
        if self._update_url:
            import webbrowser
            webbrowser.open(self._update_url)
            return
        if self._update_checker and self._update_checker.isRunning():
            return
        self._update_btn.setText("Verificando...")
        self._update_btn.setEnabled(False)
        self._update_checker = UpdateChecker()
        self._update_checker.update_available.connect(self._on_update_found)
        self._update_checker.check_done.connect(self._on_check_done)
        self._update_checker.start()

    def _on_update_found(self, version: str, url: str) -> None:
        self._update_url = url
        self._update_btn.setText(f"🔄  v{version} disponible — Descargar")
        self._update_btn.setEnabled(True)
        self._update_btn.setStyleSheet(
            "QPushButton#update_btn { background-color: #2e1a06; color: #fb923c;"
            " border: 1px solid #fb923c; border-radius: 8px; padding: 8px 20px; font-size: 13px; }"
            "QPushButton#update_btn:hover { background-color: #3d2209; }"
        )

    def _on_check_done(self) -> None:
        if self._update_url:
            return
        self._update_btn.setText("✓  Versión actualizada")
        self._update_btn.setStyleSheet(
            "QPushButton#update_btn { background-color: #0a2e1a; color: #4ade80;"
            " border: 1px solid #4ade80; border-radius: 8px; padding: 8px 20px; font-size: 13px; }"
        )
        QTimer.singleShot(3_000, self._reset_update_btn)

    def _reset_update_btn(self) -> None:
        self._update_btn.setText(f"⬆  Buscar actualizaciones  v{__version__}")
        self._update_btn.setStyleSheet("")
        self._update_btn.setEnabled(True)

    def _load(self):
        if self._thread and self._thread.isRunning():
            return
        self._subtitle.setText("Actualizando…")
        self._thread = _FetchThread(self._client, self._config.user_id, self)
        self._thread.done.connect(self._on_done)
        self._thread.fail.connect(self._on_fail)
        self._thread.start()

    def _on_done(self, appointments: List[Appointment]):
        self._clear_grid()
        now_str = datetime.now().strftime('%H:%M:%S')

        if not appointments:
            empty = QLabel("No hay eventos agendados para hoy.")
            empty.setObjectName('loading')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(empty, 0, 0, 1, self.COLS)
        else:
            name = appointments[0].professional_name
            self._subtitle.setText(
                f"{name}  —  {len(appointments)} evento(s)" if name else f"{len(appointments)} evento(s)"
            )
            for i, appt in enumerate(appointments):
                row, col = divmod(i, self.COLS)
                card = AppointmentCard(appt)
                card.confirm_requested.connect(self._on_confirm_requested)
                self._grid.addWidget(card, row, col)

        self._footer.setText(f"Última actualización: {now_str}  ·  actualiza cada minuto")

    def _on_confirm_requested(self, appointment_id: int):
        try:
            self._client.confirm_attendance(appointment_id)
        except Exception as e:
            print(f"Error confirmando asistencia: {e}")

    def _on_fail(self, msg: str):
        self._subtitle.setText(f"Error al cargar: {msg[:60]}")
        self._footer.setText("Sin conexión — reintentando en 1 minuto")

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
