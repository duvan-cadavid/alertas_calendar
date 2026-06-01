import os
import sys
from datetime import datetime

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from api.client import Appointment, SofisisClient
from config.settings import Config
from core.downloader import InstallerDownloader, launch_installer
from core.scheduler import EventScheduler
from core.updater import UpdateChecker
from core.version import __version__


def _app_icon() -> QIcon:
    base = getattr(sys, '_MEIPASS', os.path.join(os.path.dirname(__file__), '..'))
    return QIcon(os.path.join(base, 'assets', 'icon.ico'))


class TrayApp:
    def __init__(self, config: Config, app: QApplication):
        self.config = config
        self._app = app
        self._scheduler: EventScheduler | None = None
        self._alert_window = None
        self._mini_alert   = None
        self._settings_window  = None
        self._dashboard_window = None
        self._snooze_timer: QTimer | None = None

        self._update_url: str = ""
        self._update_checker: UpdateChecker | None = None
        self._downloader: InstallerDownloader | None = None
        self._update_action = None
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._start_update_check)
        self._update_timer.start(6 * 3600 * 1_000)  # re-verificar cada 6 horas
        QTimer.singleShot(15_000, self._start_update_check)  # primera verificación a los 15s

        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_app_icon())
        self._tray.setToolTip(f"Alertas de Calendarios — Sofisis  v{__version__}")
        self._tray.setVisible(True)
        self._tray.messageClicked.connect(self._on_notification_clicked)
        self._setup_menu()

    # ── Menú ──────────────────────────────────────────────────────
    def _setup_menu(self):
        menu = QMenu()

        self._status_item = menu.addAction("⬤  Sin configurar")
        self._status_item.setEnabled(False)

        menu.addSeparator()
        menu.addAction("📅  Ver agenda de hoy",      self.show_dashboard)
        menu.addAction("🎬  Grabar pantalla",         self.show_recorder)
        menu.addAction("🔔  Probar alerta ahora",     self._test_alert)
        menu.addSeparator()
        menu.addAction("⚙  Configuración",           self.show_settings)
        self._update_action = menu.addAction("🔄  Nueva versión disponible", self._install_update)
        self._update_action.setVisible(False)
        menu.addSeparator()
        import sys
        if sys.platform == 'win32':
            menu.addAction("✕  Cerrar aplicación", self._app.quit)
        else:
            lock = menu.addAction("🔒  Para cerrar: ./detener.sh")
            lock.setEnabled(False)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._recorder_window = None

    # ── Navegación ────────────────────────────────────────────────
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_dashboard()

    def show_dashboard(self, fullscreen: bool = False):
        if self._dashboard_window and self._dashboard_window.isVisible():
            self._dashboard_window.raise_()
            self._dashboard_window.activateWindow()
            return
        if not self.config.is_configured():
            self.show_settings()
            return
        from ui.dashboard_window import DashboardWindow
        self._dashboard_window = DashboardWindow(self.config)
        self._show_on_primary(self._dashboard_window, maximized=fullscreen)

    @staticmethod
    def _show_on_primary(window, maximized: bool = False):
        """Muestra la ventana ocupando el 100% del monitor primario."""
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        window.setGeometry(geo)
        window.show()

    def show_recorder(self):
        if self._recorder_window and self._recorder_window.isVisible():
            self._recorder_window.raise_()
            self._recorder_window.activateWindow()
            return
        from ui.recorder_window import RecorderWindow
        self._recorder_window = RecorderWindow(self.config)
        self._recorder_window.show()

    def show_settings(self):
        if self._settings_window and self._settings_window.isVisible():
            self._settings_window.raise_()
            return
        from ui.login_window import SettingsWindow
        self._settings_window = SettingsWindow(self.config, self._on_config_saved)
        self._settings_window.show()

    # ── Prueba manual ─────────────────────────────────────────────
    def _test_alert(self):
        """Dispara inmediatamente una alerta de prueba con el próximo evento del día."""
        if not self.config.is_configured():
            self.show_settings()
            return
        try:
            client = SofisisClient(self.config.server_url, self.config.api_token, self.config.timezone)
            appointments = client.get_today_appointments(self.config.user_id)
            now = datetime.now().astimezone()
            # Buscar el siguiente evento futuro o el más cercano
            future = [a for a in appointments if a.start_date >= now]
            target = future[0] if future else (appointments[0] if appointments else None)
            if target:
                self._show_alert(target)
            else:
                self._tray.showMessage(
                    "Sin eventos",
                    "No hay eventos agendados para hoy.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4_000,
                )
        except Exception as e:
            self._tray.showMessage(
                "Error",
                str(e),
                QSystemTrayIcon.MessageIcon.Critical,
                6_000,
            )

    # ── Scheduler ─────────────────────────────────────────────────
    def start_scheduler(self):
        self._scheduler = EventScheduler(self.config)
        self._scheduler.five_min_alert.connect(self._on_5min)
        self._scheduler.event_start_alert.connect(self._on_start)
        self._scheduler.connection_error.connect(self._on_error)
        self._scheduler.connection_ok.connect(self._on_ok)
        self._scheduler.start()

    def stop_scheduler(self):
        if self._scheduler:
            self._scheduler.stop()
            self._scheduler = None

    def _on_config_saved(self, new_config: Config):
        self.config = new_config
        if self._scheduler:
            self._scheduler.restart(new_config)
        else:
            self.start_scheduler()

    # ── Alertas ───────────────────────────────────────────────────
    def _on_5min(self, appt: Appointment):
        
        from ui.mini_alert import MiniAlert
        self._mini_alert = MiniAlert(appt, self.config.minutes_before_warning)
        self._mini_alert.confirmed.connect(self._on_attendance_confirmed)
        self._mini_alert.destroyed.connect(lambda: setattr(self, '_mini_alert', None))

    def _on_start(self, appt: Appointment):
        self._show_alert(appt)

    def _show_alert(self, appt: Appointment):
        # Ignorar solo si ya hay una alerta visible — no si hay referencia colgante
        if self._alert_window is not None and self._alert_window.isVisible():
            return
        self._alert_window = None  # limpiar referencia colgante si existía

        # Ocultar el dashboard para que no tape la alerta
        if self._dashboard_window and self._dashboard_window.isVisible():
            self._dashboard_window.hide()

        
        from ui.alert_window import AlertWindow
        self._alert_window = AlertWindow(appt)
        self._alert_window.confirmed.connect(self._on_attendance_confirmed)
        self._alert_window.snoozed.connect(self._on_snoozed)
        self._alert_window.cancelled.connect(self._on_cancelled)
        self._alert_window.destroyed.connect(self._on_alert_destroyed)
        self._alert_window.show()

    def _on_alert_destroyed(self):
        self._alert_window = None
        

    def _on_attendance_confirmed(self, appt: Appointment):
        try:
            client = SofisisClient(self.config.server_url, self.config.api_token, self.config.timezone)
            client.confirm_attendance(appt.id)
        except Exception:
            pass
        

    # ── Posponer ──────────────────────────────────────────────────
    def _on_snoozed(self, appt: Appointment, minutes: int):
        
        self._tray.showMessage(
            "Evento pospuesto",
            f"⏸ Se recordará en {minutes} minuto{'s' if minutes != 1 else ''}.",
            QSystemTrayIcon.MessageIcon.Information,
            4_000,
        )
        if self._snooze_timer:
            self._snooze_timer.stop()
        self._snooze_timer = QTimer()
        self._snooze_timer.setSingleShot(True)
        self._snooze_timer.timeout.connect(lambda: self._show_alert(appt))
        self._snooze_timer.start(minutes * 60 * 1_000)

    # ── Cancelar tarea ────────────────────────────────────────────
    def _on_cancelled(self, appt: Appointment, new_observations: str):
        try:
            client = SofisisClient(self.config.server_url, self.config.api_token, self.config.timezone)
            client.update_observations(appt.id, new_observations)
            self._tray.showMessage(
                "Tarea cancelada",
                f"✗ '{appt.text}' marcada como EVENTO CANCELADO.",
                QSystemTrayIcon.MessageIcon.Warning,
                6_000,
            )
        except Exception as e:
            self._tray.showMessage(
                "Error al cancelar",
                f"No se pudo actualizar la tarea: {e}",
                QSystemTrayIcon.MessageIcon.Critical,
                8_000,
            )
        

    # ── Auto-update ───────────────────────────────────────────────
    def _start_update_check(self) -> None:
        if self._update_checker and self._update_checker.isRunning():
            return
        self._update_checker = UpdateChecker()
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.start()

    def _on_update_available(self, version: str, url: str) -> None:
        self._update_url = url
        self._update_action.setText(f"🔄  Instalar v{version}")
        self._update_action.setVisible(True)
        self._tray.showMessage(
            f"Actualización disponible — v{version}",
            "Haz clic aquí para instalar ahora.",
            QSystemTrayIcon.MessageIcon.Information,
            8_000,
        )

    def _on_notification_clicked(self) -> None:
        if self._update_url:
            self._install_update()

    def _install_update(self) -> None:
        if not self._update_url:
            return
        if self._downloader and self._downloader.isRunning():
            return
        self._update_action.setText("⬇  Descargando...")
        self._update_action.setEnabled(False)
        self._tray.showMessage(
            "Descargando actualización",
            "Por favor espera, esto puede tardar unos segundos...",
            QSystemTrayIcon.MessageIcon.Information,
            5_000,
        )
        self._downloader = InstallerDownloader(self._update_url)
        self._downloader.done.connect(self._on_download_done)
        self._downloader.error.connect(self._on_download_error)
        self._downloader.start()

    def _on_download_done(self, path: str) -> None:
        self._tray.showMessage(
            "Instalando actualización",
            "El instalador se abrirá ahora. La app se cerrará para completar la instalación.",
            QSystemTrayIcon.MessageIcon.Information,
            4_000,
        )
        launch_installer(path)
        QTimer.singleShot(2_000, self._app.quit)

    def _on_download_error(self, msg: str) -> None:
        self._update_action.setText("🔄  Reintentar actualización")
        self._update_action.setEnabled(True)
        self._tray.showMessage(
            "Error al descargar",
            f"No se pudo descargar la actualización: {msg[:80]}",
            QSystemTrayIcon.MessageIcon.Critical,
            6_000,
        )

    # ── Estado ────────────────────────────────────────────────────
    def _on_error(self, msg: str):
        
        self._status_item.setText(f"⬤  Error: {msg[:70]}")
        self._tray.setToolTip(f"Alertas — Error de conexión")

    def _on_ok(self, event_count: int):
        hora = datetime.now().strftime('%H:%M')
        self._status_item.setText(f"⬤  Activo — {event_count} eventos hoy ({hora})")
        
        self._tray.setToolTip(f"Alertas de Calendarios — {event_count} eventos hoy")
