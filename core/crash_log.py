"""Global uncaught-exception logger.

A Windows client (Jonathan) reported the app closing outright when clicking
"Iniciar grabación" — no error dialog, nothing to go on. PyQt6 doesn't
reliably surface an unhandled exception raised inside a Qt slot the way a
plain Python script would (sometimes it's just printed to a console window
nobody sees, since this ships as a windowed .exe with no console attached);
this installs `sys.excepthook` so any such exception is at least written to
disk before the process would otherwise die silently.

This does NOT catch a hard native crash (a segfault inside a ctypes
callback, or a Qt `qFatal`) — those never reach Python's exception
machinery at all. It only helps for a normal unhandled Python exception,
which is still the far more likely case. Read alongside recorder.log (see
core/recorder.py) by the "Reportar un problema" flow — core/bug_report.py.
"""
import sys
import traceback
from datetime import datetime
from pathlib import Path

CRASH_LOG_PATH = Path.home() / '.alertas_calendario' / 'crash.log'


def install() -> None:
    CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    previous_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            with open(CRASH_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(f'\n=== {datetime.now().isoformat(timespec="seconds")} ===\n')
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass  # nunca dejar que el logger de crashes cause otro crash
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def tail(max_chars: int = 4000) -> str:
    """Últimos max_chars del crash.log, o '' si no existe/está vacío."""
    if not CRASH_LOG_PATH.exists():
        return ''
    try:
        text = CRASH_LOG_PATH.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return ''
    return text[-max_chars:]
