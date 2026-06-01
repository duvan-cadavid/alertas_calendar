import re
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo


@dataclass
class Appointment:
    id: int
    text: str
    start_date: datetime
    end_date: datetime
    customer_name: str
    service_name: str
    observations: str
    professional_name: str
    calendar_id: int
    confirmed: bool = False
    assisted: bool = False


def _name_from_label(field) -> str:
    """Extrae el nombre de un campo label "Nombre | ID", devuelve solo el nombre."""
    raw = ''
    if isinstance(field, dict):
        raw = str(field.get('label', '') or '')
    elif field:
        raw = str(field)
    return raw.split('|')[0].strip()


def _strip_html(text: str) -> str:
    if not text:
        return ''
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = (clean
             .replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
             .replace('&nbsp;', ' ').replace('&#39;', "'").replace('&quot;', '"'))
    clean = re.sub(r'[ \t]+', ' ', clean)
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    return clean.strip()


def _fmt(dt: datetime) -> str:
    """Hora local sin zona horaria — formato que Sofisis espera en filtros."""
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


class SofisisClient:
    _ENDPOINT = '/api/v1/schedule/appointment/'

    def __init__(self, server_url: str, api_token: str, timezone: str = 'America/Bogota'):
        self.server_url = server_url.rstrip('/')
        self._tz = ZoneInfo(timezone)
        self._session = requests.Session()
        self._session.headers.update({
            'X-API-TOKEN': api_token,
            'Accept': 'application/json',
        })
        self._session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _parse_dt(self, value: str) -> datetime:
        """Parsea fecha del API. El servidor devuelve hora local sin zona — se adjunta la zona configurada."""
        if not value:
            return datetime.now(self._tz)
        clean = value.replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._tz)
        return dt

    def _build(self, item: dict) -> Appointment:
        service = _name_from_label(item.get('element')) or item.get('elements', '')
        cal = item.get('calendar') or {}
        return Appointment(
            id=item['id'],
            text=item.get('text') or 'Sin título',
            start_date=self._parse_dt(item.get('start_date', '')),
            end_date=self._parse_dt(item.get('end_date', '')),
            customer_name=_name_from_label(item.get('customer')),
            service_name=service,
            observations=_strip_html(item.get('observations') or ''),
            professional_name=(item.get('calendar__user__full_name') or '').strip(),
            calendar_id=cal.get('id', 0) if isinstance(cal, dict) else 0,
            confirmed=bool(item.get('confirmed', False)),
            assisted=bool(item.get('assisted', False)),
        )

    def _fetch(self, params: dict) -> list:
        url = self.server_url + self._ENDPOINT
        resp = self._session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get('results', data) if isinstance(data, dict) else data

    def test_connection(self, user_id: str) -> str:
        now = datetime.now(self._tz).replace(tzinfo=None)
        params = {
            'calendar__user': user_id,
            'start_date__gte': _fmt(now),
            '_page_size': 1,
        }
        results = self._fetch(params)
        if results:
            name = (results[0].get('calendar__user__full_name') or '').strip()
            return f"Conectado — {name}" if name else "Conectado correctamente"
        return "Conectado correctamente"

    def get_upcoming_appointments(self, user_id: str, hours_ahead: int = 4) -> List[Appointment]:
        now_naive = datetime.now(self._tz).replace(tzinfo=None)
        from_dt = now_naive - timedelta(minutes=5)
        to_dt   = now_naive + timedelta(hours=hours_ahead)

        params = {
            'calendar__user': user_id,
            'start_date__gte': _fmt(from_dt),
            'start_date__lte': _fmt(to_dt),
            '_ordering': 'start_date',
            '_page_size': 50,
        }
        raw = self._fetch(params)
        appointments = [self._build(i) for i in raw]

        from_tz = from_dt.replace(tzinfo=self._tz)
        to_tz   = to_dt.replace(tzinfo=self._tz)
        return [a for a in appointments if from_tz <= a.start_date <= to_tz]

    def get_today_appointments(self, user_id: str) -> List[Appointment]:
        today = datetime.now(self._tz).date()
        start = datetime(today.year, today.month, today.day, 0, 0, 0)
        end   = datetime(today.year, today.month, today.day, 23, 59, 59)

        params = {
            'calendar__user': user_id,
            'start_date__gte': _fmt(start),
            'start_date__lte': _fmt(end),
            '_ordering': 'start_date',
            '_page_size': 200,
        }
        raw = self._fetch(params)
        appointments = [self._build(i) for i in raw]

        start_tz = start.replace(tzinfo=self._tz)
        end_tz   = end.replace(tzinfo=self._tz)
        return [a for a in appointments if start_tz <= a.start_date <= end_tz]

    def confirm_attendance(self, appointment_id: int) -> None:
        now = datetime.now(self._tz)
        url = f'{self.server_url}{self._ENDPOINT}{appointment_id}/'
        resp = self._session.patch(url, json={
            'assisted': True,
            'attended': now.strftime('%H:%M:%S'),
        }, timeout=15)
        resp.raise_for_status()

    def update_observations(self, appointment_id: int, observations: str) -> None:
        url = f'{self.server_url}{self._ENDPOINT}{appointment_id}/'
        resp = self._session.patch(url, json={'observations': observations}, timeout=15)
        resp.raise_for_status()
