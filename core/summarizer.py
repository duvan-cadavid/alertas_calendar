from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_config import get_groq_api_key

_SYSTEM = (
    'Eres un asistente especializado en analizar transcripciones de reuniones '
    'y tareas profesionales en español latinoamericano. '
    'Eres preciso, conciso y estructurado. '
    'Nunca inventas información que no esté en la transcripción.'
)

# ~400 tokens for system + prompt template; reserve the rest for transcription text.
# The cap is the account's tokens-per-minute quota, not the model's 131k context
# window: a single long recording must still fit in one minute's budget.
_MAX_TRANSCRIPT_CHARS = 40_000  # ≈ 10 000 tokens, leaves headroom for prompt overhead

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


class SummarizerThread(QThread):
    """Generate a structured meeting summary from transcription using Groq LLM."""
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
            text = self._text
            if len(text) > _MAX_TRANSCRIPT_CHARS:
                text = text[:_MAX_TRANSCRIPT_CHARS] + '\n\n[Transcripción truncada por longitud]'
            client = Groq(api_key=self._api_key)
            resp = client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': _PROMPT.format(text=text)},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            self.done.emit(resp.choices[0].message.content.strip())
        except ImportError:
            self.error.emit(
                'El módulo de resumen no está disponible.\n'
                'Reinicia la aplicación para instalar las dependencias automáticamente.'
            )
        except Exception as e:
            self.error.emit(self._friendly_error(e))

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
