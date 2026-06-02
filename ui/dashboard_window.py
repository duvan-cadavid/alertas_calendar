import os
import sys
from datetime import datetime, date, timedelta
from typing import List

from PyQt6.QtCore import Qt, QTimer, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGridLayout, QFrame, QSizePolicy, QApplication,
)

from api.client import Appointment, GoujanaClient
from config.settings import Config
from core.meeting_links import extract_meeting_url
from core.downloader import InstallerDownloader, launch_installer
from core.updater import UpdateChecker
from core.version import __version__


def _logo_pixmap(size: int = 52) -> QPixmap:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, 'assets', 'icon.png')
    px = QPixmap(path)
    if px.isNull():
        return px
    return px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)

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

QPushButton#bar_btn {
    background-color: #1e1e2e; color: #a6adc8;
    border: 1px solid #313244; border-radius: 8px;
    padding: 8px 4px; font-size: 13px;
}
QPushButton#bar_btn:hover  { background-color: #313244; color: #cdd6f4; }
QPushButton#bar_btn:pressed { background-color: #45475a; }

QPushButton#bar_btn_update_ready {
    background-color: #1e3a5f; color: #89b4fa;
    border: 2px solid #89b4fa; border-radius: 8px;
    padding: 8px 4px; font-size: 13px; font-weight: bold;
}
QPushButton#bar_btn_update_ready:hover { background-color: #264a73; }

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

    def __init__(self, client: GoujanaClient, user_id: str, parent=None):
        super().__init__(parent)
        self._client = client
        self._user_id = user_id

    def run(self):
        try:
            self.done.emit(self._client.get_today_appointments(self._user_id))
        except Exception as e:
            self.fail.emit(str(e))


class AppointmentCard(QFrame):
    confirm_requested = pyqtSignal(int)

    def __init__(self, appt: Appointment):
        super().__init__()
        self.setObjectName('card')
        self._appt = appt
        status = _status(appt)
        self.setStyleSheet(_CARD_STYLES[status])
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._confirm_btn = None
        self._build(appt, status)

    @staticmethod
    def _selectable(lbl: QLabel) -> QLabel:
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        lbl.setCursor(Qt.CursorShape.IBeamCursor)
        return lbl

    def _build(self, appt: Appointment, status: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        time_lbl = self._selectable(QLabel(f"⏰ {_fmt(appt.start_date)}  —  {_fmt(appt.end_date)}"))
        time_lbl.setObjectName('card_time')
        top.addWidget(time_lbl)
        top.addStretch()
        badge_text = _badge_text(status)
        if badge_text:
            badge = QLabel(badge_text)
            badge.setObjectName('card_badge')
            top.addWidget(badge)
        layout.addLayout(top)

        title = self._selectable(QLabel(appt.text))
        title.setObjectName('card_title')
        title.setWordWrap(True)
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('background-color: rgba(255,255,255,0.08);')
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        if appt.customer_name:
            info = self._selectable(QLabel(f"👤  {appt.customer_name}"))
            info.setObjectName('card_info')
            layout.addWidget(info)

        if appt.service_name:
            svc = self._selectable(QLabel(f"⚕  {appt.service_name}"))
            svc.setObjectName('card_info')
            layout.addWidget(svc)

        if appt.observations:
            obs = self._selectable(QLabel(
                f"📝  {appt.observations[:120]}{'…' if len(appt.observations) > 120 else ''}"))
            obs.setObjectName('card_info')
            obs.setWordWrap(True)
            layout.addWidget(obs)

        btn_row = QHBoxLayout()

        meeting_url = extract_meeting_url(appt.text, appt.observations)
        if meeting_url:
            join_btn = QPushButton("🔗  Conectarse")
            join_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            join_btn.setStyleSheet(
                "QPushButton { background-color: #1565C0; color: #fff; border: none; "
                "border-radius: 6px; font-size: 11px; font-weight: bold; padding: 5px 12px; } "
                "QPushButton:hover { background-color: #1976D2; } "
                "QPushButton:pressed { background-color: #0D47A1; }"
            )
            join_btn.clicked.connect(
                lambda checked, u=meeting_url: QDesktopServices.openUrl(QUrl(u)))
            btn_row.addWidget(join_btn)

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

    open_settings = pyqtSignal()
    open_recorder = pyqtSignal()
    test_alert    = pyqtSignal()

    def __init__(self, config: Config):
        super().__init__()
        self._config = config
        self._client = GoujanaClient(config.server_url, config.api_token, config.timezone)
        self._thread: _FetchThread | None = None
        self._update_checker: UpdateChecker | None = None
        self._downloader: InstallerDownloader | None = None
        self._update_url: str = ""
        self._update_btn: QPushButton | None = None

        self.setWindowTitle("Agenda de Hoy — Goujana Agenda")
        self.setMinimumSize(860, 600)
        self.resize(1000, 680)
        self.setStyleSheet(_STYLE)
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load)
        self._timer.start(self.REFRESH_MS)
        self._load()

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # ── Header: logo + date + subtitle ───────────────────────
        header = QHBoxLayout()
        header.setSpacing(16)

        logo_lbl = QLabel()
        px = _logo_pixmap(52)
        if not px.isNull():
            logo_lbl.setPixmap(px)
        logo_lbl.setFixedSize(52, 52)
        header.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        today = date.today()
        date_lbl = QLabel(
            f"📅  {_DAYS[today.weekday()]}  {today.day} de {_MONTHS[today.month]} {today.year}")
        date_lbl.setObjectName('header_date')
        text_col.addWidget(date_lbl)

        self._subtitle = QLabel("Cargando agenda…")
        self._subtitle.setObjectName('header_name')
        self._subtitle.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        text_col.addWidget(self._subtitle)
        header.addLayout(text_col)
        header.addStretch()

        root.addLayout(header)

        # ── Action button bar ─────────────────────────────────────
        root.addWidget(self._build_action_bar())

        # ── Separator ─────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('background-color: #313244;')
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ── Appointment grid ──────────────────────────────────────
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

        # ── Footer ────────────────────────────────────────────────
        self._footer = QLabel("Actualización automática cada minuto")
        self._footer.setStyleSheet("color: #45475a; font-size: 11px;")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._footer.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        root.addWidget(self._footer)

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        def _btn(label: str, slot) -> QPushButton:
            b = QPushButton(label)
            b.setObjectName('bar_btn')
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(slot)
            return b

        layout.addWidget(_btn('↻  Actualizar',      self._load))
        layout.addWidget(_btn('🎬  Grabar pantalla', self.open_recorder))
        layout.addWidget(_btn('⚙  Configuración',   self.open_settings))
        layout.addWidget(_btn('🔔  Probar alerta',   self.test_alert))

        self._update_btn = QPushButton(f'🔄  v{__version__}')
        self._update_btn.setObjectName('bar_btn')
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_btn.clicked.connect(self._check_for_updates)
        layout.addWidget(self._update_btn)

        return bar

    # ── Update flow ───────────────────────────────────────────────

    def _check_for_updates(self) -> None:
        if self._update_url:
            self._start_download()
            return
        if self._update_checker and self._update_checker.isRunning():
            return
        self._subtitle.setText('Verificando actualizaciones…')
        self._update_checker = UpdateChecker()
        self._update_checker.update_available.connect(self._on_update_found)
        self._update_checker.check_done.connect(self._on_check_done)
        self._update_checker.start()

    def _on_update_found(self, version: str, url: str) -> None:
        self._update_url = url
        self._subtitle.setText(f'🔄  v{version} disponible')
        self._update_btn.setText(f'🔄  Instalar v{version}')
        self._update_btn.setObjectName('bar_btn_update_ready')
        self._update_btn.setStyleSheet('')   # force Qt to re-evaluate the object name

    def _on_check_done(self) -> None:
        if self._update_url:
            return
        self._subtitle.setText('✓  Versión actualizada')
        QTimer.singleShot(3_000, self._load)

    def _start_download(self) -> None:
        if self._downloader and self._downloader.isRunning():
            return
        self._subtitle.setText('⬇  Descargando actualización…  0%')
        self._update_btn.setEnabled(False)
        self._downloader = InstallerDownloader(self._update_url)
        self._downloader.progress.connect(
            lambda p: self._subtitle.setText(f'⬇  Descargando…  {p}%'))
        self._downloader.done.connect(self._on_download_done)
        self._downloader.error.connect(self._on_download_error)
        self._downloader.start()

    def _on_download_done(self, path: str) -> None:
        self._subtitle.setText('⚙  Instalando actualización…')
        launch_installer(path)
        QTimer.singleShot(1_500, lambda: QApplication.instance().quit())

    def _on_download_error(self, msg: str) -> None:
        self._subtitle.setText(f'✗  Error al descargar: {msg[:60]}')
        self._update_btn.setEnabled(True)

    # ── Appointments ──────────────────────────────────────────────

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
