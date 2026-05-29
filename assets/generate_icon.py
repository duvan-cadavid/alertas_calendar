"""Genera el icono PNG de la aplicación. Se llama durante install.sh."""
import sys
from pathlib import Path


def generate(out_path: Path) -> None:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QPixmap, QPainter, QColor, QLinearGradient, QBrush
    from PyQt6.QtCore import Qt, QRect

    app = QApplication.instance() or QApplication(sys.argv)

    size = 256
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Fondo redondeado degradado
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, QColor('#1a1a3e'))
    grad.setColorAt(1, QColor('#0d0d1f'))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, 48, 48)

    # Cuerpo del calendario
    cx, cy, cw, ch = 24, 44, 156, 140
    p.setBrush(QColor('#e2e8f0'))
    p.drawRoundedRect(cx, cy, cw, ch, 14, 14)

    # Encabezado del calendario
    p.setBrush(QColor('#3b82f6'))
    p.drawRoundedRect(cx, cy, cw, 46, 14, 14)
    p.drawRect(cx, cy + 28, cw, 18)

    # Argollas
    for rx in [cx + 38, cx + 94]:
        p.setBrush(QColor('#1e293b'))
        p.drawRoundedRect(rx, cy - 14, 14, 30, 7, 7)
        p.setBrush(QColor('#bfdbfe'))
        p.drawRoundedRect(rx + 2, cy - 12, 10, 26, 5, 5)

    # Celdas de la cuadrícula del calendario
    sq, gap = 18, 7
    sx, sy = cx + 14, cy + 60
    for row in range(3):
        for col in range(5):
            xc = sx + col * (sq + gap)
            yc = sy + row * (sq + gap)
            if row == 0 and col == 0:
                p.setBrush(QColor('#ef4444'))  # hoy
            else:
                p.setBrush(QColor('#94a3b8'))
            p.drawRoundedRect(xc, yc, sq, sq, 4, 4)

    # Campana (esquina inferior derecha)
    bx, by, bs = 148, 130, 100
    p.setBrush(QColor('#f59e0b'))
    p.drawEllipse(bx, by, bs, bs)
    p.setBrush(QColor('#fbbf24'))
    p.drawEllipse(bx + 4, by + 2, bs - 8, bs - 8)
    # Interior oscuro
    p.setBrush(QColor('#1a1a3e'))
    inner = 44
    p.drawEllipse(bx + (bs - inner) // 2, by + (bs - inner) // 2, inner, inner)
    # ! dentro
    p.setBrush(QColor('#f59e0b'))
    p.drawRoundedRect(bx + bs // 2 - 4, by + bs // 4, 8, 28, 4, 4)
    p.drawEllipse(bx + bs // 2 - 4, by + bs // 4 + 34, 8, 8)

    p.end()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    px.save(str(out_path))


if __name__ == '__main__':
    out = Path(__file__).parent / 'icon.png'
    generate(out)
    print(f'Icono generado: {out}')
