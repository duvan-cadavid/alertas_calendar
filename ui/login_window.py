from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFormLayout, QGroupBox, QMessageBox, QSpinBox,
)

from api.client import SofisisClient
from config.settings import Config

_STYLE = """
    QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-family: 'Segoe UI', 'Ubuntu', Arial, sans-serif;
        font-size: 14px;
    }
    QGroupBox {
        border: 1px solid #313244;
        border-radius: 8px;
        margin-top: 14px;
        padding: 14px 12px 10px 12px;
        font-weight: bold;
        color: #89b4fa;
        font-size: 13px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }
    QLineEdit, QSpinBox {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 6px;
        padding: 8px 12px;
        color: #cdd6f4;
        font-size: 14px;
        min-height: 20px;
    }
    QLineEdit:focus, QSpinBox:focus {
        border-color: #89b4fa;
    }
    QPushButton#save_btn {
        background-color: #89b4fa;
        color: #1e1e2e;
        border: none;
        border-radius: 8px;
        padding: 12px 30px;
        font-weight: bold;
        font-size: 15px;
        min-width: 160px;
    }
    QPushButton#save_btn:hover { background-color: #b4d0ff; }
    QPushButton#save_btn:pressed { background-color: #6699d8; }
    QPushButton#test_btn {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #45475a;
        border-radius: 8px;
        padding: 10px 24px;
        font-size: 14px;
        min-width: 140px;
    }
    QPushButton#test_btn:hover { background-color: #45475a; }
    QLabel#help {
        color: #6c7086;
        font-size: 12px;
        font-style: italic;
    }
    QLabel#title {
        font-size: 22px;
        font-weight: bold;
        color: #89b4fa;
    }
    QLabel#subtitle {
        color: #6c7086;
        font-size: 13px;
    }
"""


class SettingsWindow(QWidget):
    def __init__(self, config: Config, on_save=None):
        super().__init__()
        self.config = config
        self._on_save = on_save
        self.setWindowTitle("Configuración — Alertas de Calendarios")
        self.setMinimumWidth(540)
        self.setStyleSheet(_STYLE)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        title = QLabel("Alertas de Calendarios")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel("Notificaciones de agenda en tiempo real — Sofisis")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        layout.addSpacing(6)

        # ── Conexión ──────────────────────────────────────────────
        g1 = QGroupBox("Conexión al servidor")
        f1 = QFormLayout(g1)
        f1.setSpacing(12)
        f1.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._url = QLineEdit(self.config.server_url)
        self._url.setPlaceholderText("https://miempresa.sofisis.com")
        f1.addRow("URL del servidor:", self._url)

        self._token = QLineEdit(self.config.api_token)
        self._token.setPlaceholderText("Token de 32 caracteres")
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        f1.addRow("API Token:", self._token)

        layout.addWidget(g1)

        # ── Profesional ───────────────────────────────────────────
        g2 = QGroupBox("Identificación del profesional")
        f2 = QFormLayout(g2)
        f2.setSpacing(12)
        f2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._user_id = QLineEdit(self.config.user_id)
        self._user_id.setPlaceholderText("Ej: 42")
        f2.addRow("ID de usuario:", self._user_id)

        help_lbl = QLabel(
            "Encuéntralo en la URL al editar tu perfil en Sofisis  "
            "(ej: /base_model_s/user/42/change/)"
        )
        help_lbl.setObjectName("help")
        help_lbl.setWordWrap(True)
        f2.addRow("", help_lbl)

        layout.addWidget(g2)

        # ── Alertas ───────────────────────────────────────────────
        g3 = QGroupBox("Alertas")
        f3 = QFormLayout(g3)
        f3.setSpacing(12)
        f3.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._minutes = QSpinBox()
        self._minutes.setRange(1, 30)
        self._minutes.setValue(self.config.minutes_before_warning)
        self._minutes.setSuffix(" minutos antes")
        f3.addRow("Aviso previo:", self._minutes)

        layout.addWidget(g3)

        layout.addSpacing(8)

        # ── Botones ───────────────────────────────────────────────
        btn_row = QHBoxLayout()

        test = QPushButton("Probar conexión")
        test.setObjectName("test_btn")
        test.clicked.connect(self._test)
        btn_row.addWidget(test)

        btn_row.addStretch()

        save = QPushButton("Guardar y conectar")
        save.setObjectName("save_btn")
        save.clicked.connect(self._save)
        btn_row.addWidget(save)

        layout.addLayout(btn_row)

    # ──────────────────────────────────────────────────────────────
    def _test(self):
        url = self._url.text().strip()
        token = self._token.text().strip()
        user_id = self._user_id.text().strip()

        if not (url and token and user_id):
            QMessageBox.warning(self, "Campos requeridos", "Completa todos los campos antes de probar.")
            return

        try:
            result = SofisisClient(url, token).test_connection(user_id)
            QMessageBox.information(self, "Conexión exitosa", f"✓  {result}")
        except Exception as e:
            QMessageBox.critical(self, "Error de conexión", f"No se pudo conectar:\n\n{e}")

    def _save(self):
        url = self._url.text().strip()
        token = self._token.text().strip()
        user_id = self._user_id.text().strip()

        if not (url and token and user_id):
            QMessageBox.warning(self, "Campos requeridos", "Completa todos los campos antes de guardar.")
            return

        self.config.server_url = url
        self.config.api_token = token
        self.config.user_id = user_id
        self.config.minutes_before_warning = self._minutes.value()
        self.config.save()

        if self._on_save:
            self._on_save(self.config)

        QMessageBox.information(
            self, "Guardado",
            "Configuración guardada.\nLas alertas de agenda están activas."
        )
        self.close()
