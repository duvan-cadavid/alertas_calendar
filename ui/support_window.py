"""Modo soporte técnico — ventana minimalista lanzada por protocolo.

Se activa cuando el navegador abre la app vía un link
``goujanareporte://start?token=<token>&server=<url>`` (ver
``parse_support_launch`` en ``main.py``). A diferencia del resto de la app:

- NO requiere sesión ni ``Config`` (no hay ``api_token`` de usuario, no hay
  login) — la única credencial es el ``token`` de un solo propósito que ya
  viene en la URL, emitido por el ERP para ESE reporte puntual
  (``crm_s.report_issue.start``).
- NO usa ``api/client.py`` (ese cliente firma con ``X-API-TOKEN`` de sesión
  logueada, que este modo no tiene) — el envío final se hace directo con
  ``requests`` como ``multipart/form-data``.
- NO muestra la ventana grande de agenda/CRM (``ui/recorder_window.py``) ni
  ninguna otra UI de la app — solo esta ventana suelta.
- Reusa ``core.recorder.ScreenRecorder`` tal cual para la captura de
  pantalla+mic; no duplica esa lógica de ffmpeg.
- Sin transcripción/resumen (Groq) — solo texto libre del usuario.

Contrato de envío (``POST <server>/admin/crm_s/report_issue/submit/``):
multipart con ``token``, ``title``, ``description``, ``recording`` (archivo).
Sin headers de auth ni cookies: el token es la autorización completa y
actualiza el PQR que ``start`` ya creó — nunca crea uno nuevo.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import requests
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QLineEdit, QMessageBox, QApplication,
)

from core.recorder import ScreenRecorder, get_screens, ffmpeg_available

_log = logging.getLogger('recorder')

SUBMIT_ENDPOINT = '/admin/crm_s/report_issue/submit/'


class ReportSubmitThread(QThread):
    """Envía el reporte (multipart/form-data) sin depender del event loop de Qt."""

    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, server: str, token: str, title: str, description: str,
                 recording_path: Optional[str], parent=None):
        super().__init__(parent)
        self.server = server
        self.token = token
        self.title = title
        self.description = description
        self.recording_path = recording_path

    def run(self):
        try:
            submit_report(self.server, self.token, self.title,
                           self.description, self.recording_path)
            self.done.emit()
        except Exception as e:
            _log.exception('report_issue/submit failed: %s', e)
            self.error.emit(str(e))


def submit_report(server: str, token: str, title: str, description: str,
                   recording_path: Optional[str], timeout: int = 600) -> requests.Response:
    """Hace el POST multipart del contrato. Aislado de Qt para poder probarlo
    unitariamente (ver TAREA 4 del requerimiento — sin display real disponible
    para grabar de verdad en este entorno, se verifica que el POST se
    construye con los campos correctos)."""
    url = server.rstrip('/') + SUBMIT_ENDPOINT
    data = {
        'token': token,
        'title': title,
        'description': description,
    }
    files = {}
    opened = None
    try:
        if recording_path and os.path.exists(recording_path):
            opened = open(recording_path, 'rb')
            files['recording'] = (os.path.basename(recording_path), opened, 'video/mp4')
        resp = requests.post(url, data=data, files=files or None, timeout=timeout, verify=False)
        resp.raise_for_status()
        return resp
    finally:
        if opened:
            opened.close()


class SupportWindow(QWidget):
    """Ventana minimalista del modo soporte: grabar → describir → enviar."""

    def __init__(self, server: str, token: str, app: QApplication, parent=None,
                 test_mode: bool = False):
        """``test_mode=True`` es el modo desarrollador (ver TrayApp): se abre
        desde el menú de la bandeja sin un link ``goujanareporte://`` real, así
        que no hay token/server válidos todavía — se muestran editables para
        pegarlos a mano y "Enviar" queda deshabilitado hasta llenarlos. Con un
        link real (``test_mode=False``, el caso normal) esos campos ni
        aparecen: token/server ya vienen correctos en la URL."""
        super().__init__(parent)
        self._server = server
        self._token = token
        self._app = app
        self._test_mode = test_mode
        self._recorder = ScreenRecorder(self)
        self._recording_path: Optional[str] = None
        self._submit_thread: Optional[ReportSubmitThread] = None

        self.setWindowTitle('Goujana — Reporte de soporte técnico')
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel('Reportar un problema')
        title.setStyleSheet('font-size: 16px; font-weight: bold;')
        layout.addWidget(title)

        self._server_edit: Optional[QLineEdit] = None
        self._token_edit: Optional[QLineEdit] = None
        if self._test_mode:
            dev_banner = QLabel('⚠ Modo de prueba — sin link real, pega un token/server válidos.')
            dev_banner.setStyleSheet('color: #b45309; font-weight: bold;')
            dev_banner.setWordWrap(True)
            layout.addWidget(dev_banner)

            server_label = QLabel('Server (URL base del tenant):')
            layout.addWidget(server_label)
            self._server_edit = QLineEdit(self._server)
            self._server_edit.setPlaceholderText('https://ejemplo.goujana.co')
            self._server_edit.textChanged.connect(self._on_dev_fields_changed)
            layout.addWidget(self._server_edit)

            token_label = QLabel('Token de prueba:')
            layout.addWidget(token_label)
            self._token_edit = QLineEdit(self._token)
            self._token_edit.setPlaceholderText('Pega aquí un token válido de report_issue.start')
            self._token_edit.textChanged.connect(self._on_dev_fields_changed)
            layout.addWidget(self._token_edit)

        self._status_label = QLabel('Listo para grabar.')
        layout.addWidget(self._status_label)

        self._record_btn = QPushButton('● Iniciar grabación de pantalla')
        self._record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self._record_btn)

        desc_label = QLabel('¿Qué pasó?')
        layout.addWidget(desc_label)

        self._description_edit = QPlainTextEdit()
        self._description_edit.setPlaceholderText(
            'Describe brevemente el problema que encontraste…')
        self._description_edit.setFixedHeight(100)
        layout.addWidget(self._description_edit)

        btn_row = QHBoxLayout()
        self._send_btn = QPushButton('Enviar reporte')
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._send_report)
        btn_row.addWidget(self._send_btn)
        layout.addLayout(btn_row)

        self._recorder.recording_started.connect(self._on_recording_started)
        self._recorder.finished.connect(self._on_recording_finished)
        self._recorder.error.connect(self._on_recording_error)

        if not ffmpeg_available():
            self._status_label.setText(
                'FFmpeg no está disponible — no se puede grabar, pero '
                'igual puedes enviar una descripción del problema.')
            self._record_btn.setEnabled(False)
            self._send_btn.setEnabled(not self._test_mode)

        if self._test_mode:
            # Sin token/server válidos todavía — no dejar enviar hasta pegarlos.
            self._send_btn.setEnabled(False)

    # ── Modo prueba (dev) ────────────────────────────────────────────

    def _on_dev_fields_changed(self):
        self._server = self._server_edit.text().strip()
        self._token = self._token_edit.text().strip()
        has_creds = bool(self._server) and bool(self._token)
        can_record = ffmpeg_available()
        self._send_btn.setEnabled(has_creds and (bool(self._recording_path) or True))
        if not has_creds:
            self._send_btn.setEnabled(False)
            self._status_label.setText('Pega un token y un server de prueba válidos para poder enviar.')
        else:
            self._status_label.setText(
                'Listo para grabar.' if can_record else
                'FFmpeg no está disponible — igual puedes enviar una descripción.')

    # ── Grabación ─────────────────────────────────────────────────

    def _toggle_recording(self):
        if self._recorder.state == 'idle':
            screens = get_screens()
            if not screens:
                QMessageBox.warning(self, 'Sin pantallas',
                                     'No se detectó ninguna pantalla para grabar.')
                return
            out_dir = Path(tempfile.gettempdir()) / 'goujana_soporte'
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = str(out_dir / 'reporte_soporte.mp4')
            self._recorder.start(screens[0], out_path)
        else:
            self._record_btn.setEnabled(False)
            self._status_label.setText('Finalizando grabación…')
            self._recorder.stop()

    def _on_recording_started(self):
        self._record_btn.setText('■ Detener grabación')
        self._status_label.setText('Grabando…')

    def _on_recording_finished(self, path: str):
        self._recording_path = path
        self._record_btn.setText('● Grabar de nuevo')
        self._record_btn.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._status_label.setText('Grabación lista. Describe el problema y envía el reporte.')

    def _on_recording_error(self, msg: str):
        self._record_btn.setText('● Iniciar grabación de pantalla')
        self._record_btn.setEnabled(True)
        self._status_label.setText(f'Error al grabar: {msg}')

    # ── Envío ─────────────────────────────────────────────────────

    def _send_report(self):
        if self._test_mode and not (self._server and self._token):
            QMessageBox.warning(self, 'Faltan credenciales de prueba',
                                 'Pega un token y un server de prueba válidos antes de enviar.')
            return

        description = self._description_edit.toPlainText().strip()
        if not description and not self._recording_path:
            QMessageBox.warning(self, 'Reporte vacío',
                                 'Describe el problema o grábalo antes de enviar.')
            return

        self._send_btn.setEnabled(False)
        self._record_btn.setEnabled(False)
        self._status_label.setText('Enviando reporte…')

        title = 'Reporte de soporte técnico'
        self._submit_thread = ReportSubmitThread(
            self._server, self._token, title, description, self._recording_path, self)
        self._submit_thread.done.connect(self._on_submit_done)
        self._submit_thread.error.connect(self._on_submit_error)
        self._submit_thread.start()

    def _on_submit_done(self):
        self._status_label.setText('Reporte enviado. ¡Gracias!')
        QMessageBox.information(self, 'Reporte enviado',
                                 'Tu reporte fue enviado correctamente. Ya puedes cerrar esta ventana.')
        self.close()
        self._app.quit()

    def _on_submit_error(self, msg: str):
        self._send_btn.setEnabled(True)
        self._record_btn.setEnabled(True)
        self._status_label.setText(f'No se pudo enviar: {msg}')
        QMessageBox.critical(self, 'Error al enviar',
                              f'No se pudo enviar el reporte:\n\n{msg}')

    def closeEvent(self, event):
        if self._recorder.state != 'idle':
            self._recorder.stop()
        super().closeEvent(event)
