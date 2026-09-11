from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_config import get_groq_api_key

_SYSTEM = (
    'Eres un asistente especializado en analizar transcripciones de reuniones '
    'y tareas profesionales en español latinoamericano. '
    'Eres preciso, conciso y estructurado. '
    'Nunca inventas información que no esté en la transcripción.'
)

# Clientes con reuniones de 40+ min reportaron el resumen fallando justo
# después de una transcripción que sí salió bien — un transcript así de
# largo en UNA sola petición de chat se come de un golpe la cuota de
# tokens-por-minuto de la cuenta de Groq (el límite es por minuto, no por
# el contexto de 131k del modelo) y la petición completa vuelve con 429.
# Antes esto se resolvía truncando el transcript a este tamaño y resumiendo
# solo esa parte — perdía silenciosamente el resto de la reunión. Ahora,
# por encima de este umbral, se parte en fragmentos (map) y se combinan al
# final (reduce, ver _REDUCE_PROMPT): cada petición individual es chica,
# nada se descarta. Ver también core/transcriber.py, que aplica la misma
# idea del lado de la transcripción (Whisper por fragmentos de 10 min).
_CHUNK_CHARS = 12_000  # ≈ 3 000 tokens por fragmento, con margen de sobra

_PROMPT = """Analiza la siguiente transcripción y sigue estos pasos:

PASO 1 — Clasifica el tipo de evento:
- REUNIÓN: participan dos o más personas, hay diálogo, se discuten temas, se toman decisiones.
- TAREA: una persona ejecuta una actividad, explica un proceso, realiza un trabajo individual.

PASO 2 — Genera el resumen según el tipo detectado.

━━━ Si es REUNIÓN, usa exactamente esta estructura:

## 📋 Tipo de evento
Reunión

## 🗂 Temas tratados
(lista numerada de los temas discutidos, en orden de aparición)

## 📝 Resumen ejecutivo
(2-3 oraciones que describan el propósito y resultado general de la reunión)

## 🕐 Duración
Inicio: [hora de inicio si se menciona, si no: "No especificado"]
Fin: [hora de fin si se menciona, si no: "No especificado"]

## 🤝 Acuerdos y compromisos
(lista cada acuerdo con su responsable; formato: "• [acuerdo] — Responsable: [nombre o cargo]")
(si no hay: "Ninguno identificado")

━━━ Si es TAREA, usa exactamente esta estructura:

## 📋 Tipo de evento
Tarea

## 📝 Resumen de la tarea
(2-3 oraciones describiendo qué tarea se realizó y su contexto)

## ✅ Logros y resultados
(lista numerada de lo que se completó o avanzó durante la tarea)
(si no hay logros claros: "No se identificaron logros específicos")

━━━

Transcripción:
{text}"""

# ── Map: notas concisas de UN fragmento (no la plantilla final) ────────────
_MAP_PROMPT = """Este es UN FRAGMENTO de la transcripción de una reunión o tarea larga, \
no la grabación completa. Extrae en viñetas, en español, sin inventar nada que no esté \
en el texto:

- Temas tratados en este fragmento
- Decisiones, acuerdos o compromisos mencionados, con responsable si se dice
- Cualquier dato relevante (horas, cifras, nombres, tareas)

No redactes un resumen ejecutivo ni sigas ninguna plantilla — solo notas concisas de \
este fragmento, que luego se van a combinar con las de los demás fragmentos.

Fragmento:
{text}"""

# ── Reduce: combina las notas de todos los fragmentos en el resumen final ──
_REDUCE_PROMPT = """Estas son notas parciales, ya extraídas fragmento por fragmento, de \
UNA MISMA reunión o tarea larga (no reuniones distintas). Combínalas en un solo resumen \
final siguiendo estos pasos:

PASO 1 — Clasifica el tipo de evento:
- REUNIÓN: participan dos o más personas, hay diálogo, se discuten temas, se toman decisiones.
- TAREA: una persona ejecuta una actividad, explica un proceso, realiza un trabajo individual.

PASO 2 — Genera el resumen según el tipo detectado, unificando todos los fragmentos \
(no repitas "fragmento 1", "fragmento 2"; funde la información en un solo relato).

━━━ Si es REUNIÓN, usa exactamente esta estructura:

## 📋 Tipo de evento
Reunión

## 🗂 Temas tratados
(lista numerada de los temas discutidos, en orden de aparición, de todos los fragmentos)

## 📝 Resumen ejecutivo
(2-3 oraciones que describan el propósito y resultado general de la reunión completa)

## 🕐 Duración
Inicio: [hora de inicio si se menciona, si no: "No especificado"]
Fin: [hora de fin si se menciona, si no: "No especificado"]

## 🤝 Acuerdos y compromisos
(lista cada acuerdo con su responsable, de todos los fragmentos; formato: \
"• [acuerdo] — Responsable: [nombre o cargo]")
(si no hay: "Ninguno identificado")

━━━ Si es TAREA, usa exactamente esta estructura:

## 📋 Tipo de evento
Tarea

## 📝 Resumen de la tarea
(2-3 oraciones describiendo qué tarea se realizó y su contexto, uniendo todos los fragmentos)

## ✅ Logros y resultados
(lista numerada de lo que se completó o avanzó, de todos los fragmentos)
(si no hay logros claros: "No se identificaron logros específicos")

━━━

Notas parciales:
{text}"""


def _chunk_transcript(text: str, max_chars: int) -> list:
    """Parte el transcript en fragmentos de hasta max_chars, cortando solo
    entre líneas completas (cada línea ya es "[MM:SS] ..." — ver
    core/transcriber.py) para no partir una oración a la mitad."""
    lines = text.split('\n')
    chunks, current, current_len = [], [], 0
    for line in lines:
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            chunks.append('\n'.join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append('\n'.join(current))
    return chunks


class SummarizerThread(QThread):
    """Generate a structured meeting summary from transcription using Groq LLM."""
    progress = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    # Groq shut down llama-3.3-70b-versatile on 2026-08-16 and every request
    # started coming back 404 model_not_found. This is the replacement Groq
    # itself recommends for it (console.groq.com/docs/deprecations).
    MODEL = 'openai/gpt-oss-120b'

    def __init__(self, transcription: str, parent=None):
        super().__init__(parent)
        self._text = transcription
        self._api_key = get_groq_api_key()

    def run(self):
        try:
            from groq import Groq
            client = Groq(api_key=self._api_key)
            text = self._text

            if len(text) <= _CHUNK_CHARS:
                final = self._complete(client, _PROMPT.format(text=text))
            else:
                chunks = _chunk_transcript(text, _CHUNK_CHARS)
                partials = []
                for i, chunk in enumerate(chunks, start=1):
                    self.progress.emit(f'Resumiendo parte {i}/{len(chunks)}…')
                    partial = self._complete(
                        client, _MAP_PROMPT.format(text=chunk), max_tokens=700)
                    partials.append(f'--- Fragmento {i} ---\n{partial}')
                self.progress.emit('Combinando el resumen final…')
                notes = '\n\n'.join(partials)
                final = self._complete(client, _REDUCE_PROMPT.format(text=notes))

            self.done.emit(final)
        except ImportError:
            self.error.emit(
                'El módulo de resumen no está disponible.\n'
                'Reinicia la aplicación para instalar las dependencias automáticamente.'
            )
        except Exception as e:
            self.error.emit(self._friendly_error(e))

    def _complete(self, client, prompt: str, max_tokens: int = 1500) -> str:
        resp = client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {'role': 'system', 'content': _SYSTEM},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        """Map Groq API exceptions to user-friendly Spanish messages."""
        name = type(exc).__name__
        msg = str(exc)

        if 'model_not_found' in msg or 'does not exist' in msg:
            # What the previous model's shutdown looked like from the app: an
            # opaque 404 with the raw API payload pasted into the dialog.
            return (
                'El modelo de resumen ya no está disponible en Groq.\n'
                'La aplicación necesita actualizarse para usar el modelo nuevo.\n'
                'Instala la última versión desde el menú de la bandeja.'
            )
        if 'AuthenticationError' in name or '401' in msg:
            return (
                'API key de Groq inválida o expirada.\n'
                'Ve a console.groq.com para verificar tu clave.'
            )
        if 'RateLimitError' in name or '429' in msg:
            return (
                'Límite de uso de Groq alcanzado.\n'
                'Espera unos minutos e intenta de nuevo, o revisa tu plan en console.groq.com.'
            )
        if 'APIConnectionError' in name or 'connection' in msg.lower():
            return 'No se pudo conectar a Groq. Verifica tu conexión a internet.'
        if 'APITimeoutError' in name or 'timeout' in msg.lower():
            return 'Tiempo de espera agotado al conectar con Groq. Intenta de nuevo.'
        return f'Error al generar el resumen: {msg[:300]}'
