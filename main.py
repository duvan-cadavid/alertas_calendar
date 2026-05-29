import os
import signal
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication


def _app_icon() -> QIcon:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return QIcon(os.path.join(base, 'assets', 'icon.ico'))

PID_FILE = Path.home() / '.alertas_calendario' / 'alertas.pid'


def _check_single_instance() -> None:
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)  # lanza excepción si el proceso no existe
            print(f"Ya hay una instancia corriendo (PID {pid}). Saliendo.")
            sys.exit(0)
        except (ProcessLookupError, OSError):
            pass  # PID obsoleto — continuar


def _write_pid() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _cleanup_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


def main():
    _check_single_instance()
    _write_pid()

    app = QApplication(sys.argv)
    app.setApplicationName("Alertas de Calendarios")
    app.setApplicationDisplayName("Alertas de Calendarios — Sofisis")
    app.setWindowIcon(_app_icon())
    app.setQuitOnLastWindowClosed(False)

    # Permitir cierre limpio via señal (Linux) o CTRL+C
    def _on_sigterm(*_):
        _cleanup_pid()
        app.quit()

    signal.signal(signal.SIGINT, _on_sigterm)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _on_sigterm)

    from config.settings import Config
    from ui.tray import TrayApp

    config = Config.load()
    tray = TrayApp(config, app)

    if config.is_configured():
        tray.start_scheduler()
        tray.show_dashboard(fullscreen=True)
    else:
        tray.show_settings()

    exit_code = app.exec()
    _cleanup_pid()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
