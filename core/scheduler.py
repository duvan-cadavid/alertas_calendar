from datetime import datetime, timedelta
from typing import Dict, Set

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from api.client import GoujanaClient, Appointment
from config.settings import Config


class EventScheduler(QObject):
    five_min_alert    = pyqtSignal(object)   # Appointment
    event_start_alert = pyqtSignal(object)   # Appointment
    connection_error  = pyqtSignal(str)
    connection_ok     = pyqtSignal(int)      # cantidad de eventos encontrados hoy

    POLL_INTERVAL_MS = 60_000

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._client: GoujanaClient | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._notified_5min:  Set[int] = set()
        self._notified_start: Set[int] = set()
        self._start_times:    Dict[int, datetime] = {}

    def start(self) -> None:
        self._client = GoujanaClient(self.config.server_url, self.config.api_token, self.config.timezone)
        self._check()
        self._timer.start(self.POLL_INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()
        self._client = None

    def restart(self, config: Config) -> None:
        self.stop()
        self.config = config
        self._notified_5min.clear()
        self._notified_start.clear()
        self._start_times.clear()
        self.start()

    # ──────────────────────────────────────────────────────────────
    def _check(self) -> None:
        if not self._client:
            return
        try:
            # Usar get_today_appointments — mismo endpoint que ya funciona en el dashboard
            appointments = self._client.get_today_appointments(self.config.user_id)

            # Hora local con zona horaria para comparar con appt.start_date
            now        = datetime.now().astimezone()
            warn_delta = timedelta(minutes=self.config.minutes_before_warning)

            self._cleanup_old(now)

            for appt in appointments:
                time_until = appt.start_date - now

                # Pre-aviso: entre warn_delta y 0 antes del inicio
                if timedelta(0) < time_until <= warn_delta:
                    if appt.id not in self._notified_5min:
                        self._notified_5min.add(appt.id)
                        self.five_min_alert.emit(appt)

                # Pantalla completa: desde 1 min antes hasta 2 min después del inicio.
                # Ventana de 3 minutos garantiza que siempre cae dentro de un poll de 60s.
                if timedelta(minutes=-2) <= time_until <= timedelta(minutes=1):
                    if appt.id not in self._notified_start:
                        self._notified_start.add(appt.id)
                        self._start_times[appt.id] = now
                        self.event_start_alert.emit(appt)

            self.connection_ok.emit(len(appointments))

        except Exception as exc:
            self.connection_error.emit(str(exc))

    def _cleanup_old(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=3)
        stale = [eid for eid, t in self._start_times.items() if t < cutoff]
        for eid in stale:
            self._notified_start.discard(eid)
            self._notified_5min.discard(eid)
            del self._start_times[eid]
