import os
import subprocess
import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSplitter, QFrame, QApplication, QScrollArea,
    QCheckBox, QComboBox, QLineEdit, QSizePolicy,
)

_STYLE = """
QWidget {
    background-color: #11111b;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Ubuntu', Arial, sans-serif;
    font-size: 13px;
}
QLabel#title {
    font-size: 16px; font-weight: bold; color: #89b4fa;
}
QLabel#section {
    font-size: 11px; color: #6c7086; letter-spacing: 1px;
}
QLabel#filename {
    font-size: 12px; color: #a6adc8;
}
QPushButton#btn_open {
    background-color: #1e3a5f; color: #89b4fa;
    border: 1px solid #89b4fa; border-radius: 8px;
    padding: 8px 20px; font-weight: bold;
}
QPushButton#btn_open:hover { background-color: #264a73; }
QPushButton#btn_copy {
    background-color: #1e1e2e; color: #89b4fa;
    border: 1px solid #313244; border-radius: 6px;
    padding: 5px 14px; font-size: 12px;
}
QPushButton#btn_copy:hover { background-color: #313244; }
QTextEdit {
    background-color: #1e1e2e; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 8px;
    padding: 10px; font-size: 12px; line-height: 1.5;
}
QScrollBar:vertical {
    background: #181825; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #45475a; border-radius: 4px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #313244; width: 2px; }
QFrame#sep { background-color: #313244; }
QLabel#pqr_status { font-size: 12px; }
QLabel#task_status { font-size: 12px; }
QWidget#task_row {
    background-color: #1e1e2e; border: 1px solid #313244; border-radius: 8px;
}
QPushButton#btn_schedule {
    background-color: #1e3a5f; color: #89b4fa;
    border: 1px solid #89b4fa; border-radius: 8px;
    padding: 8px 18px; font-weight: bold;
}
QPushButton#btn_schedule:hover { background-color: #264a73; }
QPushButton#btn_schedule:disabled { color: #45475a; border-color: #313244; }
"""


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setObjectName('sep')
    f.setFixedHeight(1)
    return f


def _section(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName('section')
    return l


class _TaskRow(QWidget):
    """Una tarea propuesta por la IA (core/task_extractor.py) — el asesor la
    revisa/edita/descarta acá antes de que se agende nada. Nada se agenda
    solo: es el usuario quien confirma con "Agendar tareas seleccionadas"."""

    def __init__(self, task: dict, parent=None):
        super().__init__(parent)
        self.setObjectName('task_row')
        self._task = task
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self._chk_include = QCheckBox()
        self._chk_include.setChecked(True)
        top.addWidget(self._chk_include)

        self._desc_edit = QLineEdit(task.get('description', ''))
        self._desc_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top.addWidget(self._desc_edit, 1)

        self._owner_combo = QComboBox()
        self._owner_combo.addItem('Cliente', 'cliente')
        self._owner_combo.addItem('Asesor', 'asesor')
        self._owner_combo.setCurrentIndex(0 if task.get('owner') == 'cliente' else 1)
        top.addWidget(self._owner_combo)

        self._chk_meeting = QCheckBox('Implica reunión')
        self._chk_meeting.setChecked(bool(task.get('requires_meeting', False)))
        top.addWidget(self._chk_meeting)
        layout.addLayout(top)

        self._status_lbl = QLabel('')
        self._status_lbl.setObjectName('task_status')
        self._status_lbl.setStyleSheet('color:#6c7086;')
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

    def to_task(self) -> dict:
        return {
            'description': self._desc_edit.text().strip(),
            'owner': self._owner_combo.currentData(),
            'requires_meeting': self._chk_meeting.isChecked(),
        }

    def is_included(self) -> bool:
        return self._chk_include.isChecked() and bool(self._desc_edit.text().strip())

    def set_locked(self, locked: bool):
        for w in (self._chk_include, self._desc_edit, self._owner_combo, self._chk_meeting):
            w.setEnabled(not locked)

    def set_status(self, text: str, color: str = '#6c7086'):
        self._status_lbl.setStyleSheet(f'color:{color};')
        self._status_lbl.setText(text)


class RecordingResultsWindow(QWidget):
    """Full-screen results window shown after a recording is complete."""

    schedule_tasks_requested = pyqtSignal(list)   # list[dict] confirmados por el asesor

    def __init__(self, video_path: str, transcription: str, summary: str, parent=None):
        super().__init__(parent)
        self._video_path = video_path
        self.setWindowTitle('Resultado de la Grabación — Alertas de Calendarios')
        self.setStyleSheet(_STYLE)
        self.setMinimumSize(900, 600)
        self._build(video_path, transcription, summary)
        self.showMaximized()

    def _build(self, video_path: str, transcription: str, summary: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────
        header = QHBoxLayout()

        left = QVBoxLayout()
        title = QLabel('📹  Grabación completada')
        title.setObjectName('title')
        left.addWidget(title)

        fname = QLabel(os.path.basename(video_path))
        fname.setObjectName('filename')
        fname.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        left.addWidget(fname)
        header.addLayout(left)

        header.addStretch()

        btn_open = QPushButton('▶  Reproducir video')
        btn_open.setObjectName('btn_open')
        btn_open.clicked.connect(self._open_video)
        header.addWidget(btn_open)

        root.addLayout(header)

        self._pqr_status_lbl = QLabel('☁  Creando el PQR de la reunión…')
        self._pqr_status_lbl.setObjectName('pqr_status')
        self._pqr_status_lbl.setStyleSheet('color:#89b4fa;')
        self._pqr_status_lbl.setWordWrap(True)
        root.addWidget(self._pqr_status_lbl)

        root.addWidget(_sep())

        # ── Splitter: transcription | summary ─────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: transcription
        trans_widget = QWidget()
        trans_layout = QVBoxLayout(trans_widget)
        trans_layout.setContentsMargins(0, 0, 8, 0)
        trans_layout.setSpacing(6)

        trans_hdr = QHBoxLayout()
        trans_hdr.addWidget(_section('TRANSCRIPCIÓN EN ESPAÑOL'))
        trans_hdr.addStretch()
        btn_copy_t = QPushButton('Copiar')
        btn_copy_t.setObjectName('btn_copy')
        trans_hdr.addWidget(btn_copy_t)
        trans_layout.addLayout(trans_hdr)

        trans_edit = QTextEdit()
        trans_edit.setReadOnly(True)
        trans_edit.setPlainText(transcription)
        trans_layout.addWidget(trans_edit, 1)
        btn_copy_t.clicked.connect(lambda: QApplication.clipboard().setText(trans_edit.toPlainText()))

        splitter.addWidget(trans_widget)

        # Right: summary
        sum_widget = QWidget()
        sum_layout = QVBoxLayout(sum_widget)
        sum_layout.setContentsMargins(8, 0, 0, 0)
        sum_layout.setSpacing(6)

        sum_hdr = QHBoxLayout()
        sum_hdr.addWidget(_section('RESUMEN'))
        sum_hdr.addStretch()
        btn_copy_s = QPushButton('Copiar')
        btn_copy_s.setObjectName('btn_copy')
        sum_hdr.addWidget(btn_copy_s)
        sum_layout.addLayout(sum_hdr)

        sum_edit = QTextEdit()
        sum_edit.setReadOnly(True)
        sum_edit.setPlainText(summary or 'El resumen se está generando…')
        sum_layout.addWidget(sum_edit, 1)
        btn_copy_s.clicked.connect(lambda: QApplication.clipboard().setText(sum_edit.toPlainText()))

        self._sum_edit = sum_edit   # keep ref to update when summary arrives late

        splitter.addWidget(sum_widget)
        splitter.setSizes([450, 450])
        root.addWidget(splitter, 1)

        # ── Tareas resultantes (propuestas por IA, el asesor confirma) ──
        root.addWidget(_sep())
        tasks_hdr = QHBoxLayout()
        tasks_hdr.addWidget(_section('TAREAS RESULTANTES'))
        tasks_hdr.addStretch()
        self._btn_schedule = QPushButton('📅  Agendar tareas seleccionadas')
        self._btn_schedule.setObjectName('btn_schedule')
        self._btn_schedule.clicked.connect(self._on_schedule_clicked)
        self._btn_schedule.setVisible(False)   # aparece cuando llegan tareas
        tasks_hdr.addWidget(self._btn_schedule)
        root.addLayout(tasks_hdr)

        self._tasks_status_lbl = QLabel('Buscando tareas pendientes en el resumen…')
        self._tasks_status_lbl.setStyleSheet('color:#6c7086; font-size:12px;')
        root.addWidget(self._tasks_status_lbl)

        self._tasks_scroll = QScrollArea()
        self._tasks_scroll.setWidgetResizable(True)
        self._tasks_scroll.setFixedHeight(180)
        self._tasks_scroll.setVisible(False)
        tasks_inner = QWidget()
        self._tasks_layout = QVBoxLayout(tasks_inner)
        self._tasks_layout.setContentsMargins(0, 0, 8, 0)
        self._tasks_layout.setSpacing(6)
        self._tasks_layout.addStretch()
        self._tasks_scroll.setWidget(tasks_inner)
        root.addWidget(self._tasks_scroll)

        self._task_rows: list = []

    def update_summary(self, text: str):
        """Called if summary finishes after the window is already open."""
        self._sum_edit.setPlainText(text)

    # ── Tareas resultantes ────────────────────────────────────────

    def set_tasks(self, tasks: list):
        """Llamado por RecorderWindow cuando core/task_extractor.py termina."""
        for row in self._task_rows:
            row.setParent(None)
        self._task_rows = []

        if not tasks:
            self._tasks_status_lbl.setText('No se identificaron tareas pendientes en esta reunión.')
            return

        self._tasks_status_lbl.setText(
            f'{len(tasks)} tarea(s) propuesta(s) — revisa, ajusta y confirma antes de agendar.')
        for task in tasks:
            row = _TaskRow(task)
            self._task_rows.append(row)
            self._tasks_layout.insertWidget(self._tasks_layout.count() - 1, row)
        self._tasks_scroll.setVisible(True)
        self._btn_schedule.setVisible(True)

    def set_tasks_error(self, msg: str):
        self._tasks_status_lbl.setText(f'No se pudieron extraer tareas: {msg[:120]}')

    def _on_schedule_clicked(self):
        # _row_index viaja de ida y vuelta en cada task dict (el scheduler lo
        # preserva con {**t, ...}) para poder actualizar la fila correcta al
        # recibir task_scheduled/task_failed, sin depender del orden — una
        # fila puede quedar desmarcada y correr el índice de las demás.
        selected = [
            {**row.to_task(), '_row_index': i}
            for i, row in enumerate(self._task_rows) if row.is_included()
        ]
        if not selected:
            self._tasks_status_lbl.setText('Selecciona al menos una tarea para agendar.')
            return
        for row in self._task_rows:
            row.set_locked(True)
        self._btn_schedule.setEnabled(False)
        self._tasks_status_lbl.setText('☁  Agendando…')
        self.schedule_tasks_requested.emit(selected)

    def set_scheduling_status(self, text: str, color: str = '#89b4fa'):
        self._tasks_status_lbl.setStyleSheet(f'color:{color}; font-size:12px;')
        self._tasks_status_lbl.setText(text)

    def mark_task_scheduled(self, index: int, start, end, appointment_id: int):
        if 0 <= index < len(self._task_rows):
            when = start.strftime('%d/%m %I:%M %p').replace(' 0', ' ')
            self._task_rows[index].set_status(f'✓  Agendada para el {when} — cita #{appointment_id}',
                                              '#4ade80')

    def mark_task_failed(self, index: int, msg: str):
        if 0 <= index < len(self._task_rows):
            self._task_rows[index].set_status(f'✗  {msg[:150]}', '#f38ba8')

    def set_pqr_status(self, text: str, color: str = '#89b4fa'):
        """Called by RecorderWindow while it creates the PQR in the background."""
        self._pqr_status_lbl.setStyleSheet(f'color:{color};')
        self._pqr_status_lbl.setText(text)

    def _open_video(self):
        if sys.platform == 'win32':
            os.startfile(self._video_path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', self._video_path])
        else:
            subprocess.run(['xdg-open', self._video_path])
