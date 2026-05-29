import os
import subprocess
import sys
import tempfile

import requests
from PyQt6.QtCore import QThread, pyqtSignal


class InstallerDownloader(QThread):
    progress = pyqtSignal(int)   # 0-100
    done     = pyqtSignal(str)   # ruta del instalador descargado
    error    = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self) -> None:
        filename = self._url.split('/')[-1] or "setup.exe"
        dest = os.path.join(tempfile.gettempdir(), filename)
        try:
            resp = requests.get(self._url, stream=True, timeout=120)
            resp.raise_for_status()
            total = int(resp.headers.get('content-length', 0))
            downloaded = 0
            with open(dest, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=65_536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            self.progress.emit(int(downloaded / total * 100))
            self.done.emit(dest)
        except Exception as e:
            self.error.emit(str(e))


def launch_installer(path: str) -> None:
    if sys.platform == 'win32':
        subprocess.Popen([path])
    else:
        subprocess.Popen(['xdg-open', path])
