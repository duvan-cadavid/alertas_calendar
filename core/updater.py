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

    def run(self) -> None:
        try:
            resp = requests.get(
                _API_URL,
                timeout=10,
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            latest_tag = data.get("tag_name", "")
            latest_ver = latest_tag.lstrip("v")
            if _parse(latest_ver) > _parse(__version__):
                self.update_available.emit(latest_ver, data.get("html_url", ""))
        except Exception:
            pass
