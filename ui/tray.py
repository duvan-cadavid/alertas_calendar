import os
import sys
from datetime import datetime

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication, QMessageBox

from api.client import Appointment, GoujanaClient
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
        self._bug_report_thread = None
        self._recording_prompt = None
        self._rec_prompt_timer: QTimer | None = None
        self._support_test_window = None
        self._support_test_action = None
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._start_update_check)
        self._update_timer.start(6 * 3600 * 1_000)  # re-verificar cada 6 horas
        QTimer.singleShot(15_000, self._start_update_check)  # primera verificación a los 15s

        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_app_icon())
        self._tray.setToolTip(f"Goujana Agenda  v{__version__}")
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
        menu.addAction("🛟  Reportar un problema",    self._report_problem)
        menu.addSeparator()
        # Opción oculta de testing (no en Configuración): permite alternar al
        # modo soporte técnico sin depender de un link goujanareporte:// real,
        # para poder probarlo durante desarrollo — ver ui/support_window.py
        # (test_mode) y README.md § "Probar sin un link real".
        self._support_test_action = menu.addAction("🧪  Modo soporte técnico (prueba)")
        self._support_test_action.setCheckable(True)
        self._support_test_action.toggled.connect(self._toggle_support_test_mode)
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
        if not self.config.is_configured():
            self.show_settings()
            return
        if self._dashboard_window is None:
            from ui.dashboard_window import DashboardWindow
            self._dashboard_window = DashboardWindow(self.config)
            self._dashboard_window.open_settings.connect(self.show_settings)
            self._dashboard_window.open_recorder.connect(self.show_recorder)
            self._dashboard_window.test_alert.connect(self._test_alert)
            self._show_on_primary(self._dashboard_window, maximized=fullscreen)
        elif not self._dashboard_window.isVisible():
            self._show_on_primary(self._dashboard_window, maximized=False)
        self._dashboard_window.raise_()
        self._dashboard_window.activateWindow()

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
        try:
            from ui.recorder_window import RecorderWindow
            self._recorder_window = RecorderWindow(self.config)
            self._recorder_window.show()
        except Exception as e:
            # Antes esto fallaba en silencio: un ImportError (típicamente la
            # instalación quedó con una mezcla de archivos viejos/nuevos,
            # ver build/setup.iss CloseApplications) tumbaba el import sin
            # ningún aviso — el usuario veía "le doy clic en Grabar y no pasa
            # nada". Al menos ahora hay un mensaje con algo accionable.
            import logging
            logging.getLogger('recorder').error('No se pudo abrir el grabador: %s', e, exc_info=True)
            QMessageBox.critical(
                None, 'No se pudo abrir el grabador',
                f'Ocurrió un error al abrir la ventana de grabación:\n\n{e}\n\n'
                'Prueba desinstalar y reinstalar la última versión desde GitHub Releases '
                '(si el problema persiste tras reiniciar el PC), o usa "🛟 Reportar un problema" '
                'en este mismo menú para avisarnos.')

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
            client = GoujanaClient(self.config.server_url, self.config.api_token, self.config.timezone)
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
        if self._dashboard_window:
            self._dashboard_window.show()
            self._dashboard_window.raise_()
            self._dashboard_window.activateWindow()


    def _on_attendance_confirmed(self, appt: Appointment):
        try:
            client = GoujanaClient(self.config.server_url, self.config.api_token, self.config.timezone)
            client.confirm_attendance(appt.id)
        except Exception:
            pass
        # Tell the dashboard so its next 60-s refresh doesn't re-enable the button.
        if self._dashboard_window:
            self._dashboard_window.mark_confirmed(appt.id)
        self._show_recording_prompt(appt, show_cancel=False)

    def _show_recording_prompt(self, appt: Appointment, show_cancel: bool = False):
        from ui.recording_prompt import RecordingPromptWindow
        self._recording_prompt = RecordingPromptWindow(appt, show_cancel=show_cancel)
        self._recording_prompt.record_now.connect(self.show_recorder)
        self._recording_prompt.record_later.connect(
            lambda: self._snooze_recording_prompt(appt))
        self._recording_prompt.dismissed.connect(lambda: None)
        self._recording_prompt.show()

    def _snooze_recording_prompt(self, appt: Appointment):
        if self._rec_prompt_timer:
            self._rec_prompt_timer.stop()
        self._rec_prompt_timer = QTimer()
        self._rec_prompt_timer.setSingleShot(True)
        self._rec_prompt_timer.timeout.connect(
            lambda: self._show_recording_prompt(appt, show_cancel=True))
        self._rec_prompt_timer.start(5 * 60 * 1_000)
        self._tray.showMessage(
            "Grabación pospuesta",
            "⏱  Se recordará en 5 minutos.",
            QSystemTrayIcon.MessageIcon.Information,
            4_000,
        )


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
            client = GoujanaClient(self.config.server_url, self.config.api_token, self.config.timezone)
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
        self._update_checker.check_failed.connect(self._on_update_check_failed)
        self._update_checker.start()

    def _on_update_check_failed(self, msg: str) -> None:
        # Verificación automática en segundo plano (cada 6h + una a los 15s
        # de arrancar): no interrumpe con un diálogo, pero antes esto se
        # tragaba la excepción entera y no quedaba ni rastro de por qué el
        # usuario seguía viendo una versión vieja — ver core/updater.py.
        import logging
        logging.getLogger('recorder').warning('Verificación de actualización falló: %s', msg)

    # ── Modo soporte técnico (prueba/dev) ─────────────────────────────
    def _toggle_support_test_mode(self, checked: bool) -> None:
        """"Modo usuario" <-> "Modo soporte técnico (prueba)" desde el tray,
        sin necesitar un link goujanareporte:// real — ver
        ui/support_window.py (test_mode=True): token/server quedan editables
        ahí mismo porque no vienen de ningún link."""
        if checked:
            if self._support_test_window is not None:
                return
            from ui.support_window import SupportWindow
            server = self.config.server_url if self.config.is_configured() else ''
            self._support_test_window = SupportWindow(
                server, '', self._app, test_mode=True)
            self._support_test_window.destroyed.connect(self._on_support_test_window_closed)
            self._support_test_window.show()
        else:
            if self._support_test_window is not None:
                self._support_test_window.close()
                self._support_test_window = None

    def _on_support_test_window_closed(self) -> None:
        self._support_test_window = None
        if self._support_test_action is not None:
            self._support_test_action.setChecked(False)

    # ── Reportar un problema ─────────────────────────────────────────
    def _report_problem(self) -> None:
        """Junta recorder.log + crash.log y crea un PQR interno (ver
        core/bug_report.py) — pensado para casos como el de un cliente al
        que se le cerraba la app al grabar sin ningún error visible: antes
        la única forma de diagnosticarlo era pedirle el log manualmente por
        WhatsApp."""
        if not self.config.is_configured():
            self._tray.showMessage(
                "No se pudo reportar", "Configura la app primero (servidor/token).",
                QSystemTrayIcon.MessageIcon.Warning, 6_000)
            return
        if self._bug_report_thread and self._bug_report_thread.isRunning():
            return

        from PyQt6.QtWidgets import QInputDialog
        comment, ok = QInputDialog.getMultiLineText(
            None, "Reportar un problema",
            "Describe brevemente qué pasó (opcional — el log se adjunta solo):")
        if not ok:
            return

        from core.bug_report import BugReportThread
        self._bug_report_thread = BugReportThread(
            self.config.server_url, self.config.api_token, self.config.user_id, comment)
        self._bug_report_thread.done.connect(self._on_bug_report_done)
        self._bug_report_thread.error.connect(self._on_bug_report_error)
        self._tray.showMessage(
            "Enviando reporte…", "Recolectando los logs y creando el reporte.",
            QSystemTrayIcon.MessageIcon.Information, 4_000)
        self._bug_report_thread.start()

    def _on_bug_report_done(self, pqr_id: int) -> None:
        self._tray.showMessage(
            "Reporte enviado", f"Se creó el reporte #{pqr_id}. Gracias.",
            QSystemTrayIcon.MessageIcon.Information, 6_000)

    def _on_bug_report_error(self, msg: str) -> None:
        self._tray.showMessage(
            "No se pudo enviar el reporte", msg[:150],
            QSystemTrayIcon.MessageIcon.Critical, 8_000)

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
