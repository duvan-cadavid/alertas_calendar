import sys

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from core.version import __version__

_API_URL = "https://api.github.com/repos/duvan-cadavid/alertas_calendar/releases/latest"


def _parse(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.lstrip("v").split(".")[:3])
    except ValueError:
        return (0,)


class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str)  # latest_version, html_url
    check_done       = pyqtSignal()          # emitido siempre al terminar
    check_failed     = pyqtSignal(str)       # la verificación no se pudo completar (no es "no hay actualización")

    def run(self) -> None:
        # GitHub Releases only ships a Windows .exe. On Linux there is
        # nothing to auto-install — the app is updated via `git pull` (see
        # install.sh) — so this used to download the .exe anyway, fail to
        # open it with `xdg-open`, and then still self-quit 2s later
        # (tray.py/dashboard_window.py _on_download_done), leaving the user
        # with a window that opens and silently vanishes. Skip entirely.
        if sys.platform != 'win32':
            self.check_done.emit()
            return
        try:
            resp = requests.get(
                _API_URL,
                timeout=10,
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code != 200:
                # Antes esto caía silenciosamente al "no hay actualización"
                # de más abajo — un cliente reportó "le doy Actualizar y no
                # encuentra la versión nueva" sin ningún error visible, y
                # resultó indistinguible de estar realmente al día. La causa
                # más probable en Windows es rate-limit de la API de GitHub
                # sin autenticar (60 req/hora por IP — se comparte entre
                # todos los que salen por la misma IP de oficina) u otro 4xx
                # de un proxy/firewall corporativo. Sea cual sea, se avisa en
                # vez de fingir que no hay nada nuevo.
                self.check_failed.emit(
                    f'GitHub respondió {resp.status_code} al buscar la última versión.'
                )
                return
            data = resp.json()
            latest_tag = data.get("tag_name", "")
            latest_ver = latest_tag.lstrip("v")
            if _parse(latest_ver) > _parse(__version__):
                assets = data.get("assets", [])
                exe = next((a for a in assets if a["name"].endswith(".exe")), None)
                download_url = exe["browser_download_url"] if exe else data.get("html_url", "")
                self.update_available.emit(latest_ver, download_url)
        except Exception as e:
            self.check_failed.emit(f'No se pudo verificar actualizaciones: {e}')
        finally:
            self.check_done.emit()
