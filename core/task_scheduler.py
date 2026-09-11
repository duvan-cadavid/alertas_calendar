"""Busca hueco libre en la agenda del asesor y crea la cita de una tarea resultante.

La cita se crea en ``schedule.appointment`` (el mismo modelo que ya lee
api/client.py) — no se llama a Google Calendar directamente: la señal
``post_save`` de ese modelo en base_sofisis ya sincroniza cada cita nueva al
Google Calendar del asesor, generando el link de Meet automáticamente si ese
asesor tiene esa integración activa (``GoogleCalendarToken.create_meet_link``,
una bandera por-profesional, no por-cita — por eso "implica reunión" solo
queda como nota explícita en la observación, no como algo que esta app pueda
forzar por cita individual).
"""
from datetime import datetime, timedelta, time as dtime
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from api.client import Appointment, GoujanaClient

BUSINESS_START = dtime(8, 0)
BUSINESS_END = dtime(18, 0)
DEFAULT_DURATION_MIN = 30
SEARCH_DAYS_AHEAD = 7
_SLOT_STEP_MIN = 15


def find_next_slot(existing: List[Appointment], now: datetime,
                    duration_minutes: int = DEFAULT_DURATION_MIN,
                    taken: Optional[list] = None):
    """Primer hueco libre dentro de los próximos SEARCH_DAYS_AHEAD días
    hábiles, en horario laboral, que no choque con ``existing`` ni con
    ``taken`` (huecos ya asignados en este mismo lote, para no duplicar dos
    tareas a la misma hora). Devuelve (start, end) o None si no hay hueco."""
    tz = now.tzinfo
    duration = timedelta(minutes=duration_minutes)
    busy = [(a.start_date, a.end_date) for a in existing] + list(taken or [])

    day = now.date()
    for _ in range(SEARCH_DAYS_AHEAD + 1):
        if day.weekday() < 5:  # lunes(0)..viernes(4)
            day_start = datetime.combine(day, BUSINESS_START, tzinfo=tz)
            day_end = datetime.combine(day, BUSINESS_END, tzinfo=tz)
            cursor = _round_up(max(day_start, now) if day == now.date() else day_start,
                               _SLOT_STEP_MIN)
            while cursor + duration <= day_end:
                candidate_end = cursor + duration
                if not _overlaps(cursor, candidate_end, busy):
                    return cursor, candidate_end
                cursor += timedelta(minutes=_SLOT_STEP_MIN)
        day += timedelta(days=1)
    return None


def _overlaps(start: datetime, end: datetime, busy: list) -> bool:
    return any(start < b_end and end > b_start for b_start, b_end in busy)


def _round_up(dt: datetime, minutes: int) -> datetime:
    remainder = dt.minute % minutes
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    dt = dt - timedelta(minutes=remainder, seconds=dt.second, microseconds=dt.microsecond)
    return dt + timedelta(minutes=minutes)


def build_observation(description: str, owner: str, requires_meeting: bool,
                      pqr_id: Optional[int] = None) -> str:
    audit_line = (
        'El asesor debe verificar que el cliente cumplió esta tarea.' if owner == 'cliente'
        else 'El cliente debe verificar que el asesor cumplió esta tarea.'
    )
    lines = [
        f'Tarea resultante de la reunión' + (f' (PQR #{pqr_id}).' if pqr_id else '.'),
        f'Responsable: {"Cliente" if owner == "cliente" else "Asesor"}.',
        audit_line,
    ]
    if requires_meeting:
        lines.append('Esta tarea implica una reunión — coordinar videollamada.')
    lines.append(f'Descripción: {description}')
    return '\n'.join(lines)


class TaskSchedulerThread(QThread):
    """Agenda cada tarea confirmada, una por una, buscando hueco libre real
    en la agenda (no una hora fija) y sin repetir hueco entre tareas del
    mismo lote."""
    progress = pyqtSignal(str)
    task_scheduled = pyqtSignal(dict)   # {..task, 'start', 'end', 'appointment_id'}
    task_failed = pyqtSignal(dict, str)
    done = pyqtSignal()

    def __init__(self, client: GoujanaClient, user_id: str, calendar_id: int,
                 customer_id: int, tasks: list, pqr_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._client = client
        self._user_id = user_id
        self._calendar_id = calendar_id
        self._customer_id = customer_id
        self._tasks = tasks
        self._pqr_id = pqr_id

    def run(self):
        now = datetime.now(self._client.tz)
        try:
            existing = self._client.get_appointments_range(
                self._user_id, now, now + timedelta(days=SEARCH_DAYS_AHEAD + 1))
        except Exception as e:
            for t in self._tasks:
                self.task_failed.emit(t, f'No se pudo leer la agenda: {e}')
            self.done.emit()
            return

        taken: list = []
        for t in self._tasks:
            self.progress.emit(f'Agendando: {t["description"][:60]}…')
            slot = find_next_slot(existing, now, taken=taken)
            if not slot:
                self.task_failed.emit(
                    t, f'No se encontró un hueco libre en los próximos {SEARCH_DAYS_AHEAD} días.')
                continue
            start, end = slot
            observation = build_observation(
                t['description'], t['owner'], t['requires_meeting'], self._pqr_id)
            try:
                appt_id = self._client.create_appointment(
                    self._calendar_id, self._customer_id, start, end,
                    text=f'Tarea: {t["description"][:80]}', observations=observation)
                taken.append((start, end))
                self.task_scheduled.emit({**t, 'start': start, 'end': end,
                                          'appointment_id': appt_id})
            except Exception as e:
                self.task_failed.emit(t, str(e))
        self.done.emit()
