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
    customer_id: int = 0


@dataclass
class Customer:
    id: int
    full_name: str
    identification: str = ''
    email: str = ''
    phone: str = ''
    cell: str = ''

    def display_label(self) -> str:
        bits = [self.full_name]
        contact = self.identification or self.cell or self.phone or self.email
        if contact:
            bits.append(f'({contact})')
        return '  '.join(bits)


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
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


class GoujanaClient:
    _ENDPOINT = '/api/v1/schedule/appointment/'
    _USER_ENDPOINT = '/api/v1/base_model_s/user/'
    _CALENDAR_ENDPOINT = '/api/v1/schedule/calendar/'

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

    @property
    def tz(self) -> ZoneInfo:
        return self._tz

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
        customer = item.get('customer') or {}
        return Appointment(
            id=item['id'],
            text=item.get('text') or 'Sin título',
            start_date=self._parse_dt(item.get('start_date', '')),
            end_date=self._parse_dt(item.get('end_date', '')),
            customer_name=_name_from_label(customer),
            service_name=service,
            observations=_strip_html(item.get('observations') or ''),
            professional_name=(item.get('calendar__user__full_name') or '').strip(),
            calendar_id=cal.get('id', 0) if isinstance(cal, dict) else 0,
            confirmed=bool(item.get('confirmed', False)),
            assisted=bool(item.get('assisted', False)),
            customer_id=customer.get('id', 0) if isinstance(customer, dict) else 0,
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

    def get_calendar_id(self, user_id: str) -> int:
        """Id del `schedule.calendar` del profesional — lo pide crear una cita
        (campo obligatorio, sin default utilizable desde la API con token)."""
        url = self.server_url + self._CALENDAR_ENDPOINT
        params = {'user': user_id, 'active': 'True', '_page_size': 1, 'fields': 'id'}
        resp = self._session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get('results', data) if isinstance(data, dict) else data
        if not rows:
            raise ValueError(f'No se encontró un calendario activo para el usuario {user_id}.')
        return rows[0]['id']

    def get_appointments_range(self, user_id: str, start: datetime, end: datetime) -> List[Appointment]:
        """Citas del profesional entre start y end (naive, hora local) — usado
        para calcular huecos libres en la agenda al agendar tareas."""
        params = {
            'calendar__user': user_id,
            'start_date__gte': _fmt(start),
            'start_date__lte': _fmt(end),
            '_ordering': 'start_date',
            '_page_size': 500,
        }
        raw = self._fetch(params)
        return [self._build(i) for i in raw]

    def create_appointment(self, calendar_id: int, customer_id: int, start_date: datetime,
                           end_date: datetime, text: str, observations: str = '') -> int:
        """Crea una cita nueva. Al guardarse, `schedule`'s señal post_save la
        sincroniza sola a Google Calendar del profesional (con Meet si ese
        profesional tiene la integración activa) — Alertas no llama a Google
        directamente, ver core/task_scheduler.py.

        Gotcha verificado en producción y en local (base_sofisis dev):
        ``ApiSofisisView.perform_create`` no solo valida con el serializer
        DRF (que acepta el string ISO combinado sin problema) — también
        revalida con el FORMULARIO DEL ADMIN de Django
        (``_validate_with_admin_form``, util_s/api_restful/api_view.py),
        que para un ``DateTimeField`` usa el widget partido del admin
        (``AdminSplitDateTime``): espera ``start_date_0`` (fecha) y
        ``start_date_1`` (hora) por separado. Sin esas dos claves, el
        formulario del admin ve el campo vacío y el POST completo falla con
        "Este campo es requerido." en start_date/end_date, aunque el string
        combinado sí venga en el payload. Se mandan ambas formas: el string
        combinado (por si acaso lo necesita el serializer) y las partes
        sueltas (que es lo que realmente exige la revalidación del admin).
        """
        url = self.server_url + self._ENDPOINT
        start_date_local = start_date.astimezone(self._tz) if start_date.tzinfo else start_date
        end_date_local = end_date.astimezone(self._tz) if end_date.tzinfo else end_date
        payload = {
            'calendar': calendar_id,
            'customer': customer_id,
            'start_date': _fmt(start_date),
            'start_date_0': start_date_local.strftime('%Y-%m-%d'),
            'start_date_1': start_date_local.strftime('%H:%M:%S'),
            'end_date': _fmt(end_date),
            'end_date_0': end_date_local.strftime('%Y-%m-%d'),
            'end_date_1': end_date_local.strftime('%H:%M:%S'),
            'text': text,
            'observations': observations,
        }
        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()['id']

    def search_customers(self, term: str, limit: int = 15) -> List['Customer']:
        """Busca terceros marcados como cliente por identificación, celular, teléfono,
        correo o nombre (todos cubiertos por ``q``, ver base_user_admin.search_fields)."""
        term = (term or '').strip()
        if not term:
            return []
        url = self.server_url + self._USER_ENDPOINT
        params = {
            'q': term,
            'is_customer': 'True',
            '_page_size': limit,
            'fields': 'id,full_name,identification,email,phone,cell',
        }
        resp = self._session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get('results', data) if isinstance(data, dict) else data
        return [
            Customer(
                id=row['id'],
                full_name=(row.get('full_name') or '').strip(),
                identification=row.get('identification') or '',
                email=row.get('email') or '',
                phone=row.get('phone') or '',
                cell=row.get('cell') or '',
            )
            for row in rows
        ]
