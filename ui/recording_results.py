import os
import subprocess
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QSplitter, QFrame, QApplication,
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


class RecordingResultsWindow(QWidget):
    """Full-screen results window shown after a recording is complete."""

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

    def update_summary(self, text: str):
        """Called if summary finishes after the window is already open."""
        self._sum_edit.setPlainText(text)

    def _open_video(self):
        if sys.platform == 'win32':
            os.startfile(self._video_path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', self._video_path])
        else:
            subprocess.run(['xdg-open', self._video_path])
