from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_config import GROQ_API_KEY

_SYSTEM = (
    'Eres un asistente especializado en analizar transcripciones de reuniones '
    'y tareas profesionales en español latinoamericano. '
    'Eres preciso, conciso y estructurado. '
    'Nunca inventas información que no esté en la transcripción.'
)

# ~400 tokens for system + prompt template; reserve the rest for transcription text.
# Groq on_demand TPM limit for llama-3.3-70b-versatile is 12 000.
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

    MODEL = 'llama-3.3-70b-versatile'

    def __init__(self, transcription: str, parent=None):
        super().__init__(parent)
        self._text = transcription
        self._api_key = GROQ_API_KEY

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
            self.error.emit(str(e))
