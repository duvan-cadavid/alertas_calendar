import os
import signal
import subprocess
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox


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


_REQUIRED = [
    ('groq',    'groq>=0.11.0'),
    ('httpx',   'httpx'),
]


def _ensure_dependencies(app: QApplication) -> None:
    """Install any missing runtime dependencies automatically.

    In a PyInstaller bundle all packages are already embedded — a missing
    import there indicates a build problem and we just show an error.
    In source-mode (development / Linux direct run) we install via pip.
    """
    missing = []
    for module, package in _REQUIRED:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if not missing:
        return

    is_bundle = getattr(sys, 'frozen', False)

    if is_bundle:
        QMessageBox.critical(
            None,
            'Dependencias faltantes',
            'Faltan componentes en la instalación:\n\n'
            + '\n'.join(missing)
            + '\n\nPor favor descarga e instala la versión más reciente '
              'desde GitHub Releases.',
        )
        return

    # Running from source — install silently via pip
    msg = QMessageBox(
        QMessageBox.Icon.Information, 'Instalando dependencias',
        'Faltan paquetes necesarios. Instalando automáticamente…\n\n'
        + '\n'.join(missing),
    )
    msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
    msg.show()
    app.processEvents()

    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--quiet'] + missing,
        capture_output=True,
    )
    msg.close()

    if result.returncode != 0:
        QMessageBox.warning(
            None, 'Error al instalar',
            'No se pudieron instalar las dependencias automáticamente.\n\n'
            'Ejecuta manualmente:\n'
            f'  pip install {" ".join(missing)}\n\n'
            + result.stderr.decode(errors='replace')[:300],
        )


def main():
    _check_single_instance()
    _write_pid()

    app = QApplication(sys.argv)
    app.setApplicationName("Alertas de Calendarios")
    app.setApplicationDisplayName("Alertas de Calendarios — Sofisis")
    app.setWindowIcon(_app_icon())
    app.setQuitOnLastWindowClosed(False)
    _ensure_dependencies(app)

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
