"""
Icons of the GUI: the application icon, and the colored icons of the Run and Stop buttons (drawn at run time, Qt draws
them greyed out when the buttons are disabled).

The application icon is in the files of APP_ICON_DIR: the PNG image for the windows, the Dock, the taskbar and the
notifications, and the icon files of the program (.icns for the macOS app, .ico for the Windows executable). To change
it, replace them, or make them from a new image with scripts/make_icons.py.
"""
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF

APP_ICON_DIR = Path(__file__).parent / 'app-icon'  # Also in the PyInstaller builds, and in the installed package
APP_ICON_PNG = APP_ICON_DIR / 'arxorter.png'
APP_ICON_ICNS = APP_ICON_DIR / 'arxorter.icns'
APP_ICON_ICO = APP_ICON_DIR / 'arxorter.ico'

RUN_GREEN = QColor('#2ea043')
STOP_RED = QColor('#d93025')

SIZES = (16, 24, 32, 48)


def _draw_icon(draw: Callable[[QPainter, int], None], sizes: tuple[int, ...] = SIZES) -> QIcon:
    icon = QIcon()
    for size in sizes:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        draw(painter, size)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def app_icon() -> QIcon:
    return QIcon(str(APP_ICON_PNG))


def run_icon() -> QIcon:
    """
    Green triangle pointing right.
    """
    def draw(painter: QPainter, size: int):
        painter.setBrush(RUN_GREEN)
        # Slightly to the right of the center, so the triangle looks centered
        painter.drawPolygon(QPolygonF([QPointF(size * 0.22, size * 0.12), QPointF(size * 0.88, size * 0.5),
                                       QPointF(size * 0.22, size * 0.88)]))

    return _draw_icon(draw)


def stop_icon() -> QIcon:
    """
    Red square with rounded corners.
    """
    def draw(painter: QPainter, size: int):
        painter.setBrush(STOP_RED)
        radius = size * 0.12
        painter.drawRoundedRect(QRectF(size * 0.18, size * 0.18, size * 0.64, size * 0.64), radius, radius)

    return _draw_icon(draw)
