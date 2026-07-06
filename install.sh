#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "=========================================="
echo "  Alertas de Calendarios — Instalador"
echo "=========================================="
echo ""

# ── 1. Dependencias del sistema (Linux/apt) ────────────────────
echo "[1/6] Instalando dependencias del sistema..."
SYSTEM_PKGS=(
    python3
    python3-venv
    python3-pip
    curl
    libfuse2
    libxcb-cursor0
    libxcb1
    libxcb-icccm4
    libxcb-image0
    libxcb-keysyms1
    libxcb-render-util0
    libxcb-xinerama0
    libxcb-xkb1
    libxkbcommon-x11-0
)

if command -v apt-get &>/dev/null; then
    sudo apt-get install -y "${SYSTEM_PKGS[@]}" > /dev/null 2>&1 && \
        echo "  ✓  Paquetes de sistema instalados." || \
        echo "  !  No se pudieron instalar algunos paquetes (puede requerir sudo)."
else
    echo "  !  apt-get no encontrado. Instala manualmente: ${SYSTEM_PKGS[*]}"
fi

# ── 2. Entorno virtual Python ──────────────────────────────────
echo "[2/6] Preparando entorno virtual Python..."

PY=$(command -v python3)
if [ -z "$PY" ]; then
    echo "ERROR: Python 3 no está instalado."
    exit 1
fi
echo "  Python: $($PY --version)"

if [ ! -d "$APP_DIR/venv" ]; then
    $PY -m venv "$APP_DIR/venv"
fi

# ── 3. Paquetes Python ────────────────────────────────────────
echo "[3/6] Instalando paquetes Python..."
source "$APP_DIR/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$APP_DIR/requirements.txt"
echo "  ✓  Paquetes Python instalados."

# ── 4. Icono y acceso directo en el menú ─────────────────────
echo "[4/6] Instalando ícono y acceso directo..."

python3 "$APP_DIR/assets/generate_icon.py"
ICON_PATH="$APP_DIR/assets/icon.png"

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/alertas-calendarios.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Alertas de Calendarios
GenericName=Notificaciones de Agenda
Comment=Alertas en tiempo real de eventos agendados — Sofisis
Exec="$APP_DIR/iniciar.sh"
Icon=$ICON_PATH
Terminal=false
Categories=Office;ProjectManagement;
Keywords=agenda;calendario;sofisis;alertas;
StartupNotify=false
EOF

chmod +x "$DESKTOP_DIR/alertas-calendarios.desktop"
gio set "$DESKTOP_DIR/alertas-calendarios.desktop" metadata::trusted true 2>/dev/null || true

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "  ✓  Acceso directo instalado."

# ── 5. Autostart al iniciar sesión ───────────────────────────
echo "[5/6] Configurando inicio automático..."

AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/alertas-calendarios.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Alertas de Calendarios
Comment=Alertas en tiempo real de eventos agendados — Sofisis
Exec="$APP_DIR/iniciar.sh"
Icon=$ICON_PATH
Terminal=false
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
EOF

chmod +x "$AUTOSTART_DIR/alertas-calendarios.desktop"
echo "  ✓  Inicio automático configurado."

# ── 6. Meetily (transcripción y resumen de reuniones) ─────────
echo "[6/6] Instalando Meetily (transcripción de reuniones)..."

GITHUB_REPO="duvan-cadavid/alertas_calendar"
MEETILY_DIR="$HOME/.local/opt/meetily"
MEETILY_BIN="$MEETILY_DIR/meetily.AppImage"

install_meetily() {
    local api_url="https://api.github.com/repos/$GITHUB_REPO/releases"
    local asset_url

    asset_url=$(curl -fsSL "$api_url" 2>/dev/null | python3 -c "
import json, sys
releases = json.load(sys.stdin)
for rel in releases:
    if not rel['tag_name'].startswith('meetily-'):
        continue
    for asset in rel['assets']:
        if asset['name'].endswith('.AppImage'):
            print(asset['browser_download_url'])
            sys.exit(0)
" 2>/dev/null)

    if [ -z "$asset_url" ]; then
        echo "  !  No se encontró release 'meetily-*' con AppImage en $GITHUB_REPO."
        echo "     Ejecuta el workflow 'Build Meetily Linux' en GitHub Actions y reinstala."
        return 1
    fi

    mkdir -p "$MEETILY_DIR"
    echo "  Descargando: $asset_url"
    curl -fL --progress-bar -o "$MEETILY_BIN.tmp" "$asset_url" || return 1
    mv "$MEETILY_BIN.tmp" "$MEETILY_BIN"
    chmod +x "$MEETILY_BIN"

    cat > "$DESKTOP_DIR/meetily.desktop" << MEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Meetily
GenericName=Asistente de Reuniones
Comment=Transcripción y resumen local de reuniones
Exec="$MEETILY_BIN"
Terminal=false
Categories=Office;AudioVideo;
Keywords=reunion;transcripcion;resumen;meetily;
StartupNotify=false
MEOF
    chmod +x "$DESKTOP_DIR/meetily.desktop"
    return 0
}

if install_meetily; then
    echo "  ✓  Meetily instalado en $MEETILY_BIN"
elif [ -x "$MEETILY_BIN" ]; then
    echo "  !  Falló la actualización; se conserva la versión ya instalada."
else
    echo "  !  Meetily no se instaló. La app de alertas funciona igualmente."
fi

# Permisos de los scripts
chmod +x "$APP_DIR/iniciar.sh"
chmod +x "$APP_DIR/detener.sh"

echo ""
echo "=========================================="
echo "  ✓  Instalación completada."
echo "=========================================="
echo ""
echo "  La aplicación inicia automáticamente al encender el equipo."
echo ""
echo "  Comandos:"
echo "    Iniciar:  ./iniciar.sh"
echo "    Detener:  ./detener.sh"
echo ""
