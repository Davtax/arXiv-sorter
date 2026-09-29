"""
Icons of the GUI, drawn at run time: the application icon (until an icon file is added in logo/), and the colored
icons of the Run and Stop buttons. Qt draws them greyed out when the buttons are disabled.
"""
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygonF

APP_ICON_TEXT = 'aXs'
ARXIV_RED = QColor('#b31b1b')
RUN_GREEN = QColor('#2ea043')
STOP_RED = QColor('#d93025')

SIZES = (16, 24, 32, 48, 64, 128, 256)


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
    def draw(painter: QPainter, size: int):
        painter.setBrush(ARXIV_RED)
        radius = size * 0.22
        painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

        font = QFont()
        font.setBold(True)
        font.setPixelSize(max(int(size * 0.4), 6))
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 92)  # Three letters fit in the small sizes
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(QRectF(0, 0, size, size * 0.96), Qt.AlignmentFlag.AlignCenter, APP_ICON_TEXT)

    return _draw_icon(draw)


def run_icon() -> QIcon:
    """
    Green triangle pointing right.
    """
    def draw(painter: QPainter, size: int):
        painter.setBrush(RUN_GREEN)
        # Slightly to the right of the center, so the triangle looks centered
        painter.drawPolygon(QPolygonF([QPointF(size * 0.22, size * 0.12), QPointF(size * 0.88, size * 0.5),
                                       QPointF(size * 0.22, size * 0.88)]))

    return _draw_icon(draw, SIZES[:4])


def stop_icon() -> QIcon:
    """
    Red square with rounded corners.
    """
    def draw(painter: QPainter, size: int):
        painter.setBrush(STOP_RED)
        radius = size * 0.12
        painter.drawRoundedRect(QRectF(size * 0.18, size * 0.18, size * 0.64, size * 0.64), radius, radius)

    return _draw_icon(draw, SIZES[:4])
