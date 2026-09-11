"""Crea el PQR de la reunión (crm_s.requestscomplaints) y adjunta la grabación.

Sigue las instrucciones del proyecto hermano base_sofisis
(.claude/skills/requerimiento/create_pqr.py y
support_chat_s/data/docs/api-escritura-registros.md) para escribir en el ERP
de producción vía su API v1:

- El PQR SIEMPRE se crea en el tenant 6155 / ``company`` 56529
  (GOUJANA SOFTWARE ERP SAS), sin importar en qué compañía esté la sesión del
  token del profesional — de ahí el ``?_company=56529`` explícito en cada
  llamada y el ``"company": 56529`` repetido en el body (gotchas 1 y 2 del
  script hermano).
- ``date``/``end_date`` van explícitos: el default del modelo es un datetime,
  y la API rechaza eso donde espera un date (gotcha 3).
- Autenticación por header ``X-Api-Token`` (gotcha 4), el mismo token que ya
  usa GoujanaClient para leer la agenda del profesional.
- El adjunto de la grabación va como comentario sobre el PQR, no en el propio
  registro: los adjuntos de este ERP son ``django_comments.Comment`` con un
  campo ``image`` (ver app_s/services/health/video_consultation/services/
  consent.py del proyecto hermano) — la API expone ese modelo en
  ``/api/v1/django_comments/comment/`` y resuelve el ``content_type`` a partir
  de ``content_type_app_label``/``content_type_model`` para no tener que
  conocer el pk interno del ContentType.
"""
import os

import requests


COMPANY = 56529          # GOUJANA SOFTWARE ERP SAS (tenant 6155). Nunca 10852.
BRANCH = 1640             # Cabañas
CONCEPT_ACTA_REUNION = 62  # crm_s.Concept "Acta de reunión", creado para este flujo
PRIORITY_MEDIA = '2'
STATE_CLOSED = '4'        # "Caso cerrado con éxito"

_PQR_ENDPOINT = '/api/v1/crm_s/requestscomplaints/'
_COMMENT_ENDPOINT = '/api/v1/django_comments/comment/'


class PQRClient:
    """Cliente mínimo para crear el PQR y su comentario con adjunto.

    Usa el token del profesional (``Config.api_token``) — ya verificado que
    puede leer/escribir en company 56529 vía ``?_company`` aunque su sesión
    por defecto sea otra compañía.
    """

    def __init__(self, server_url: str, api_token: str):
        self.server_url = server_url.rstrip('/')
        self._session = requests.Session()
        self._session.headers.update({'X-Api-Token': api_token})
        self._session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def create_pqr(self, customer_id: int, title: str, description_html: str) -> int:
        """Crea el PQR y devuelve su id."""
        from datetime import date
        today = date.today().isoformat()
        payload = {
            'company': COMPANY,          # gotcha 2
            'customer': customer_id,
            'branch': BRANCH,
            'concept': CONCEPT_ACTA_REUNION,
            'priority': PRIORITY_MEDIA,
            'state': STATE_CLOSED,
            'date': today,               # gotcha 3
            'end_date': today,
            'title': title,
            'description': description_html,
        }
        url = f'{self.server_url}{_PQR_ENDPOINT}?_company={COMPANY}'  # gotcha 1
        resp = self._session.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()['id']

    def add_comment(self, pqr_id: int, text: str, attach_path: str = None) -> None:
        """Agrega un comentario al PQR, opcionalmente con un archivo adjunto.

        ``attach_path`` va como multipart en el campo ``image`` (el nombre que
        usa el modelo Comment de este ERP para cualquier tipo de adjunto, no
        solo imágenes — ver el docstring del módulo).
        """
        url = f'{self.server_url}{_COMMENT_ENDPOINT}'
        data = {
            'content_type_app_label': 'crm_s',
            'content_type_model': 'requestscomplaints',
            'object_pk': str(pqr_id),
            'comment': text,
            'is_public': 'True',
        }
        if attach_path and os.path.exists(attach_path):
            with open(attach_path, 'rb') as f:
                files = {'image': (os.path.basename(attach_path), f)}
                resp = self._session.post(url, data=data, files=files, timeout=600)
        else:
            resp = self._session.post(url, data=data, timeout=60)
        resp.raise_for_status()


def summary_to_html(summary_text: str) -> str:
    """Convierte el resumen (markdown con ##, **, listas) a HTML para la descripción."""
    try:
        import markdown
        return markdown.markdown(summary_text, extensions=['nl2br'])
    except ImportError:
        return _plain_text_to_html(summary_text)


def transcript_to_html(transcript_text: str) -> str:
    """Envuelve la transcripción (texto plano con timestamps) en HTML simple."""
    return '<h2>Transcripción completa</h2>\n' + _plain_text_to_html(transcript_text)


def _plain_text_to_html(text: str) -> str:
    from html import escape
    paragraphs = [p.strip() for p in (text or '').split('\n') if p.strip()]
    return '\n'.join(f'<p>{escape(p)}</p>' for p in paragraphs) or '<p>(vacío)</p>'


def build_pqr_description(summary_text: str, transcript_text: str) -> str:
    """Primera parte: resumen en HTML. Segunda parte: transcripción en HTML."""
    return summary_to_html(summary_text) + '\n<hr />\n' + transcript_to_html(transcript_text)
