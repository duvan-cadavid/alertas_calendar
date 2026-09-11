#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$APP_DIR/venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    notify-send "Alertas de Calendarios" "No instalado — ejecuta ./install.sh" 2>/dev/null || true
    exit 1
fi

# Forzar XCB (X11/XWayland): en sesiones Wayland (GNOME/Ubuntu por defecto),
# Qt intenta el backend "wayland" nativo y el compositor ignora el
# setGeometry() que usa la app para posicionar el dashboard a pantalla
# completa — la ventana queda invisible aunque el proceso siga corriendo
# (visible en la bandeja). XCB evita ese problema. Se respeta si el usuario
# ya definió QT_QPA_PLATFORM explícitamente.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

# Ejecutar directamente el Python del venv sin necesitar activarlo
exec "$PYTHON" "$APP_DIR/main.py"


