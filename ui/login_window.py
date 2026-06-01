from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFormLayout, QGroupBox, QMessageBox, QComboBox,
    QFileDialog, QScrollArea, QFrame,
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
    QLineEdit, QSpinBox, QComboBox {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 6px;
        padding: 8px 12px;
        color: #cdd6f4;
        font-size: 14px;
        min-height: 20px;
    }
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
        border-color: #89b4fa;
    }
    QComboBox::drop-down { border: none; padding-right: 8px; }
    QComboBox QAbstractItemView {
        background-color: #313244;
        border: 1px solid #45475a;
        color: #cdd6f4;
        selection-background-color: #45475a;
        outline: none;
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
    QPushButton#save_btn:hover  { background-color: #b4d0ff; }
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
    QScrollArea {
        border: none;
        background: transparent;
    }
    QScrollArea > QWidget > QWidget {
        background: transparent;
    }
    QScrollBar:vertical {
        background: #181825;
        width: 8px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #45475a;
        border-radius: 4px;
        min-height: 24px;
    }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical { height: 0; }
    QFrame#divider { background-color: #313244; }
"""

_TIMEZONES = [
    ('America/Bogota',                  'Bogotá, Lima, Quito  (UTC−5)'),
    ('America/Lima',                    'Lima  (UTC−5)'),
    ('America/Guayaquil',               'Guayaquil  (UTC−5)'),
    ('America/Panama',                  'Panamá  (UTC−5)'),
    ('America/Caracas',                 'Caracas  (UTC−4)'),
    ('America/La_Paz',                  'La Paz  (UTC−4)'),
    ('America/Santiago',                'Santiago  (UTC−3/−4)'),
    ('America/Argentina/Buenos_Aires',  'Buenos Aires  (UTC−3)'),
    ('America/Sao_Paulo',               'São Paulo  (UTC−3)'),
    ('America/Mexico_City',             'Ciudad de México  (UTC−6)'),
    ('America/New_York',                'Nueva York  (UTC−5/−4)'),
    ('America/Chicago',                 'Chicago  (UTC−6/−5)'),
    ('America/Los_Angeles',             'Los Ángeles  (UTC−8/−7)'),
    ('Europe/Madrid',                   'Madrid  (UTC+1/+2)'),
    ('UTC',                             'UTC'),
]


class SettingsWindow(QWidget):
    def __init__(self, config: Config, on_save=None):
        super().__init__()
        self.config = config
        self._on_save = on_save
        self.setWindowTitle("Configuración — Alertas de Calendarios")
        self.setMinimumSize(560, 500)
        self.resize(580, 680)
        self.setStyleSheet(_STYLE)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        # ── Encabezado (fijo, fuera del scroll) ───────────────────
        title = QLabel("Alertas de Calendarios")
        title.setObjectName("title")
        root.addWidget(title)

        subtitle = QLabel("Notificaciones de agenda en tiempo real — Sofisis")
        subtitle.setObjectName("subtitle")
        root.addWidget(subtitle)

        root.addSpacing(12)

        # ── Scroll area con todos los grupos ──────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        form = QVBoxLayout(container)
        form.setContentsMargins(0, 0, 12, 8)
        form.setSpacing(10)

        # Conexión
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
        form.addWidget(g1)

        # Profesional
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
        form.addWidget(g2)

        # Alertas
        g3 = QGroupBox("Alertas")
        f3 = QFormLayout(g3)
        f3.setSpacing(12)
        f3.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._minutes = QComboBox()
        for mins in [2, 5, 10, 20]:
            self._minutes.addItem(f"{mins} minutos antes", mins)
        _warning_idx = next(
            (i for i, m in enumerate([2, 5, 10, 20])
             if m == self.config.minutes_before_warning), 1
        )
        self._minutes.setCurrentIndex(_warning_idx)
        f3.addRow("Aviso previo:", self._minutes)
        self._timezone = QComboBox()
        for tz_id, tz_label in _TIMEZONES:
            self._timezone.addItem(tz_label, userData=tz_id)
        idx = next((i for i, (tz_id, _) in enumerate(_TIMEZONES)
                    if tz_id == self.config.timezone), 0)
        self._timezone.setCurrentIndex(idx)
        f3.addRow("Zona horaria:", self._timezone)
        form.addWidget(g3)

        # Transcripción e IA
        g_ai = QGroupBox("Transcripción e IA  (Groq)")
        f_ai = QFormLayout(g_ai)
        f_ai.setSpacing(12)
        f_ai.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._groq_key = QLineEdit(self.config.groq_api_key)
        self._groq_key.setPlaceholderText("gsk_…")
        self._groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        f_ai.addRow("API Key:", self._groq_key)
        groq_help = QLabel(
            "Obtén tu clave gratis en console.groq.com  —  "
            "incluye ~2 horas/día de transcripción sin costo"
        )
        groq_help.setObjectName("help")
        groq_help.setWordWrap(True)
        f_ai.addRow("", groq_help)
        form.addWidget(g_ai)

        # Grabaciones
        g4 = QGroupBox("Grabaciones de pantalla")
        f4 = QFormLayout(g4)
        f4.setSpacing(12)
        f4.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self._rec_folder = QLineEdit(self.config.recordings_folder)
        self._rec_folder.setPlaceholderText("Carpeta donde se guardan las grabaciones")
        folder_row.addWidget(self._rec_folder)
        browse_rec = QPushButton("···")
        browse_rec.setObjectName("test_btn")
        browse_rec.setFixedWidth(44)
        browse_rec.clicked.connect(self._browse_recordings)
        folder_row.addWidget(browse_rec)
        f4.addRow("Carpeta:", folder_row)
        form.addWidget(g4)

        form.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # ── Divisor ───────────────────────────────────────────────
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        root.addSpacing(12)
        root.addWidget(divider)
        root.addSpacing(12)

        # ── Botones (fijos, siempre visibles) ─────────────────────
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
        root.addLayout(btn_row)

    # ── Acciones ──────────────────────────────────────────────────

    def _browse_recordings(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Seleccionar carpeta de grabaciones', self._rec_folder.text())
        if folder:
            self._rec_folder.setText(folder)

    def _test(self):
        url   = self._url.text().strip()
        token = self._token.text().strip()
        uid   = self._user_id.text().strip()
        if not (url and token and uid):
            QMessageBox.warning(self, "Campos requeridos",
                                "Completa todos los campos antes de probar.")
            return
        try:
            tz = self._timezone.currentData()
            result = SofisisClient(url, token, timezone=tz).test_connection(uid)
            QMessageBox.information(self, "Conexión exitosa", f"✓  {result}")
        except Exception as e:
            QMessageBox.critical(self, "Error de conexión", f"No se pudo conectar:\n\n{e}")

    def _save(self):
        url   = self._url.text().strip()
        token = self._token.text().strip()
        uid   = self._user_id.text().strip()
        if not (url and token and uid):
            QMessageBox.warning(self, "Campos requeridos",
                                "Completa todos los campos antes de guardar.")
            return
        self.config.server_url             = url
        self.config.api_token              = token
        self.config.user_id                = uid
        self.config.minutes_before_warning = self._minutes.currentData()
        self.config.timezone               = self._timezone.currentData()
        self.config.recordings_folder      = self._rec_folder.text().strip() or self.config.recordings_folder
        self.config.groq_api_key           = self._groq_key.text().strip()
        self.config.save()
        if self._on_save:
            self._on_save(self.config)
        QMessageBox.information(
            self, "Guardado",
            "Configuración guardada.\nLas alertas de agenda están activas."
        )
        self.close()
