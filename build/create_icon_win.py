"""
Convierte assets/icon.png a assets/icon.ico para el .exe de Windows.
Ejecutar en Windows antes de hacer el build: python build/create_icon_win.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

def main():
    try:
        from PIL import Image
        img = Image.open(ROOT / 'assets' / 'icon.png')
        img.save(
            ROOT / 'assets' / 'icon.ico',
            format='ICO',
            sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)],
        )
        print('icon.ico generado correctamente.')
    except ImportError:
        # Si no hay Pillow, usar PyQt6 para exportar
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QIcon, QPixmap
        app = QApplication(sys.argv)
        px = QPixmap(str(ROOT / 'assets' / 'icon.png'))
        px.save(str(ROOT / 'assets' / 'icon.ico'))
        print('icon.ico generado con PyQt6.')

if __name__ == '__main__':
    main()
