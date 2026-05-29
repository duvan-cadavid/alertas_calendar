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

    def run(self) -> None:
        try:
            resp = requests.get(
                _API_URL,
                timeout=10,
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                latest_tag = data.get("tag_name", "")
                latest_ver = latest_tag.lstrip("v")
                if _parse(latest_ver) > _parse(__version__):
                    assets = data.get("assets", [])
                    exe = next((a for a in assets if a["name"].endswith(".exe")), None)
                    download_url = exe["browser_download_url"] if exe else data.get("html_url", "")
                    self.update_available.emit(latest_ver, download_url)
        except Exception:
            pass
        finally:
            self.check_done.emit()
