import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

# Esquema de protocolo del "modo soporte técnico": el navegador lo invoca como
# goujanareporte://start?token=<token>&server=<url_base_del_tenant> (registrado
# en build/setup.iss, sección [Registry]). Windows pasa la URL completa como
# argv[1] al abrir la app; ver parse_support_launch() y ui/support_window.py.
SUPPORT_PROTOCOL = 'goujanareporte'


def _app_icon() -> QIcon:
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return QIcon(os.path.join(base, 'assets', 'icon.ico'))


def parse_support_launch(argv) -> Optional[Tuple[str, str]]:
    """Si algún argumento es un link goujanareporte://, devuelve (token, server).

    Devuelve None si no se lanzó en modo soporte, o si el link llegó
    incompleto (falta token o server) — en ese caso el caller debe tratarlo
    como lanzamiento normal en vez de intentar un modo soporte a medias.
    """
    for arg in argv[1:]:
        if not isinstance(arg, str) or not arg.startswith(f'{SUPPORT_PROTOCOL}://'):
            continue
        parsed = urlparse(arg)
        qs = parse_qs(parsed.query)
        token = (qs.get('token') or [''])[0]
        server = (qs.get('server') or [''])[0]
        if token and server:
            return token, server
        return None
    return None

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
    ('groq',     'groq>=0.11.0'),
    ('httpx',    'httpx'),
    ('markdown', 'markdown>=3.4'),
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


def _run_support_mode(app: QApplication, token: str, server: str) -> int:
    """Modo soporte técnico: ventana minimalista, sin login, sin agenda/CRM.

    No usa el single-instance lock ni el PID file de la app normal — es un
    proceso corto e independiente (puede coexistir con la app de agenda ya
    corriendo en la bandeja) y no debe quedar bloqueado por ella ni bloquearla.
    """
    from ui.support_window import SupportWindow

    app.setQuitOnLastWindowClosed(True)
    window = SupportWindow(server, token, app)
    window.show()
    return app.exec()


def main():
    from core import crash_log
    crash_log.install()

    support_launch = parse_support_launch(sys.argv)

    app = QApplication(sys.argv)
    app.setApplicationName("Goujana Agenda")
    app.setApplicationDisplayName("Goujana Agenda")
    app.setWindowIcon(_app_icon())

    if support_launch is not None:
        token, server = support_launch
        exit_code = _run_support_mode(app, token, server)
        sys.exit(exit_code)

    _check_single_instance()
    _write_pid()

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
