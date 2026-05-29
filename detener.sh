#!/bin/bash
PID_FILE="$HOME/.alertas_calendario/alertas.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Alertas de Calendarios detenida (PID $PID)."
        rm -f "$PID_FILE"
    else
        echo "El proceso no estaba corriendo. Limpiando PID obsoleto."
        rm -f "$PID_FILE"
    fi
else
    # Fallback por nombre de proceso
    if pkill -f "python3 main.py"; then
        echo "Proceso detenido."
    else
        echo "Alertas de Calendarios no está corriendo."
    fi
fi
