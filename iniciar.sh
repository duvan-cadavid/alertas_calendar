#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$APP_DIR/venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    notify-send "Alertas de Calendarios" "No instalado — ejecuta ./install.sh" 2>/dev/null || true
    exit 1
fi

# Ejecutar directamente el Python del venv sin necesitar activarlo
exec "$PYTHON" "$APP_DIR/main.py"


