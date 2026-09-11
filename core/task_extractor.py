"""Extrae del resumen final la lista de tareas pendientes / acuerdos resultantes.

Cada tarea queda con: descripción, dueño (cliente/asesor) e "implica reunión".
La IA solo PROPONE — el asesor revisa y confirma en la ventana de resultados
antes de que se agende nada (core/task_scheduler.py hace el agendamiento real).
"""
import json

from PyQt6.QtCore import QThread, pyqtSignal

from core.ai_config import get_groq_api_key

_SYSTEM = (
    'Eres un asistente que extrae tareas pendientes de un resumen de reunión. '
    'Respondes SOLO con JSON válido, sin texto adicional ni markdown.'
)

_PROMPT = """A partir de este resumen de una reunión o tarea, extrae la lista de \
tareas pendientes / acuerdos resultantes que quedaron por ejecutar (NO tareas ya \
completadas, NO temas solo mencionados sin compromiso de acción concreto).

Para cada tarea determina:
- "description": descripción breve y clara de la tarea.
- "owner": "cliente" si la debe ejecutar el cliente, "asesor" si la debe ejecutar \
el profesional/asesor. Usa tu mejor juicio según quién se comprometió a hacerla.
- "requires_meeting": true si la tarea implica coordinar una reunión o videollamada \
para completarla o darle seguimiento, false si no la necesita (enviar un documento, \
hacer un pago, revisar algo por su cuenta, etc.).

Responde SOLO con un array JSON, sin texto adicional ni markdown, con esta forma:
[{{"description": "...", "owner": "cliente", "requires_meeting": false}}]

Si no hay ninguna tarea pendiente clara, responde exactamente: []

Resumen:
{text}"""


class TaskExtractorThread(QThread):
    done = pyqtSignal(list)   # list[dict] — puede ser []
    error = pyqtSignal(str)

    MODEL = 'openai/gpt-oss-120b'

    def __init__(self, summary_text: str, parent=None):
        super().__init__(parent)
        self._text = summary_text
        self._api_key = get_groq_api_key()

    def run(self):
        try:
            from groq import Groq
            client = Groq(api_key=self._api_key)
            resp = client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': _PROMPT.format(text=self._text)},
                ],
                temperature=0.2,
                max_tokens=1200,
            )
            raw = resp.choices[0].message.content.strip()
            self.done.emit(_parse(raw))
        except ImportError:
            self.error.emit('El módulo de IA no está disponible.')
        except Exception as e:
            self.error.emit(f'No se pudieron extraer las tareas: {e}')


def _parse(raw: str) -> list:
    """Tolerante a que el modelo meta fences de markdown o texto alrededor
    del array — busca el primer '[' ... último ']' como respaldo."""
    text = raw.strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:]
    data = _try_json(text)
    if data is None:
        start, end = text.find('['), text.rfind(']')
        if start != -1 and end != -1:
            data = _try_json(text[start:end + 1])
    if not isinstance(data, list):
        return []

    tasks = []
    for item in data:
        if not isinstance(item, dict):
            continue
        description = str(item.get('description', '')).strip()
        if not description:
            continue
        owner = str(item.get('owner', '')).strip().lower()
        owner = owner if owner in ('cliente', 'asesor') else 'cliente'
        tasks.append({
            'description': description,
            'owner': owner,
            'requires_meeting': bool(item.get('requires_meeting', False)),
        })
    return tasks


def _try_json(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return None
