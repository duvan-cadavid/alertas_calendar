from PyQt6.QtCore import QThread, pyqtSignal

_SYSTEM = (
    'Eres un asistente especializado en resumir reuniones y citas profesionales '
    'en español latinoamericano. Eres preciso, conciso y estructurado.'
)

_PROMPT = """Analiza la siguiente transcripción y genera un resumen estructurado.

**Resumen ejecutivo**
(2-3 oraciones que describan de qué trató la reunión o cita)

**Temas tratados**
(lista de los principales temas discutidos)

**Acuerdos y compromisos**
(lo que se acordó hacer; escribe "Ninguno identificado" si no hay)

**Próximos pasos**
(acciones pendientes; escribe "Ninguno identificado" si no hay)

Transcripción:
{text}"""


class SummarizerThread(QThread):
    """Generate a structured meeting summary from transcription using Groq LLM."""
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    MODEL = 'llama-3.3-70b-versatile'

    def __init__(self, transcription: str, api_key: str, parent=None):
        super().__init__(parent)
        self._text = transcription
        self._api_key = api_key

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
                temperature=0.3,
                max_tokens=1500,
            )
            self.done.emit(resp.choices[0].message.content.strip())
        except ImportError:
            self.error.emit('groq no instalado.')
        except Exception as e:
            self.error.emit(str(e))
