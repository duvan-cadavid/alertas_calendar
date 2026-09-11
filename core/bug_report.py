"""«Reportar un problema»: junta los logs locales y crea un PQR interno.

No es un PQR de un cliente sobre una reunión — es un bug de la app misma.
Va al cliente/concepto fijos de core/pqr_client.py (BUG_REPORT_CUSTOMER /
CONCEPT_SOPORTE_TECNICO), en estado "En proceso" (queda abierto para
revisión, a diferencia de las actas de reunión que se crean ya cerradas).

El caso que motivó esto: un cliente reportó que la app se cerraba entera al
dar "Iniciar grabación", sin ningún mensaje de error — sin este botón, la
única forma de diagnosticarlo era pedirle por WhatsApp que buscara
manualmente %USERPROFILE%\\.alertas_calendario\\recorder.log y lo mandara.
"""
import html
import platform
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core import crash_log
from core.pqr_client import (
    PQRClient, BUG_REPORT_CUSTOMER, CONCEPT_SOPORTE_TECNICO,
    PRIORITY_ALTA, STATE_EN_PROCESO,
)
from core.recorder import LOG_PATH as RECORDER_LOG_PATH
from core.version import __version__


def _tail(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ''
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return ''
    return text[-max_chars:]


def _pre_block(title: str, text: str) -> str:
    body = html.escape(text) if text else '(vacío)'
    return f'<h3>{html.escape(title)}</h3>\n<pre style="white-space:pre-wrap;">{body}</pre>'


def build_report_description(user_comment: str, user_id: str) -> str:
    parts = [
        f'<p><strong>Versión:</strong> {html.escape(__version__)}</p>',
        f'<p><strong>Sistema:</strong> {html.escape(platform.platform())}</p>',
        f'<p><strong>user_id (Goujana):</strong> {html.escape(str(user_id))}</p>',
    ]
    if user_comment.strip():
        parts.append(_pre_block('Descripción del usuario', user_comment))
    parts.append(_pre_block('recorder.log (últimas líneas)', _tail(RECORDER_LOG_PATH)))
    parts.append(_pre_block('crash.log — excepciones no capturadas (últimas líneas)',
                             crash_log.tail()))
    return '\n'.join(parts)


class BugReportThread(QThread):
    done = pyqtSignal(int)   # pqr id
    error = pyqtSignal(str)

    def __init__(self, server_url: str, api_token: str, user_id: str,
                 user_comment: str, parent=None):
        super().__init__(parent)
        self._server_url = server_url
        self._api_token = api_token
        self._user_id = user_id
        self._user_comment = user_comment

    def run(self):
        try:
            client = PQRClient(self._server_url, self._api_token)
            title = f'[Alertas] Reporte de problema — {self._user_id} — v{__version__}'
            description = build_report_description(self._user_comment, self._user_id)
            pqr_id = client.create_pqr(
                BUG_REPORT_CUSTOMER, title, description,
                concept=CONCEPT_SOPORTE_TECNICO,
                priority=PRIORITY_ALTA,
                state=STATE_EN_PROCESO,
            )
            # El recorder.log completo va también como adjunto del comentario
            # — la descripción solo trae la cola, para no pasarse de tamaño.
            attach = str(RECORDER_LOG_PATH) if RECORDER_LOG_PATH.exists() else None
            client.add_comment(pqr_id, 'recorder.log completo adjunto.', attach_path=attach)
            self.done.emit(pqr_id)
        except Exception as e:
            self.error.emit(str(e))
