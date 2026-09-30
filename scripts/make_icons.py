"""
Make the icon files of arXorter from a square PNG image of at least 1024 × 1024 pixels (e.g. exported from
logo/arxorter-icon.af). The image replaces the PNG of the application icon, and the .icns (macOS app) and .ico
(Windows executable) files next to it are made from it, all in src/arxorter/gui/app-icon. In the .icns file, the
image is drawn on a white squircle, as the other icons of macOS.

Usage: python scripts/make_icons.py [path to the PNG image]
Without an image, the icon files are made again from the current PNG.
"""
import math
import shutil
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from arxorter.gui.icons import APP_ICON_ICNS, APP_ICON_ICO, APP_ICON_PNG

MIN_SIZE = 1024  # pixels, the largest image of the .icns file
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)  # Windows, up to 256 pixels
# macOS: type of each image in the .icns file and its size in pixels (the @2x types are for Retina displays)
ICNS_TYPES = {b'icp4': 16, b'icp5': 32, b'icp6': 64, b'ic07': 128, b'ic08': 256, b'ic09': 512, b'ic10': 1024,
              b'ic11': 32, b'ic12': 64, b'ic13': 256, b'ic14': 512}
# macOS icon grid: the squircle is 824 of 1024 pixels, centered, and the margin leaves room for its shadow
SQUIRCLE_SIZE = 824 / 1024  # Of the icon
SQUIRCLE_EXPONENT = 5  # Superellipse |x|^n + |y|^n = 1, close to the continuous corners of the macOS icons
CONTENT_SIZE = 0.8  # Of the squircle, for the visible part of the image
SHADOW_OFFSET = 12 / 1024  # Down, of the icon
SHADOW_BLUR = 16  # Times the shadow is scaled down to blur it
SHADOW_ALPHA = 70  # Of 255


def png(image: QImage, size: int) -> bytes:
    """
    The image scaled to the size, as a PNG file.
    """
    scaled = image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    scaled.save(buffer, 'PNG')
    return bytes(buffer.data())


def squircle(rect: QRectF, points: int = 720) -> QPainterPath:
    """
    Squircle (superellipse) filling the rectangle.
    """
    path = QPainterPath()
    center, radius = rect.center(), rect.width() / 2
    for index in range(points):
        angle = 2 * math.pi * index / points
        cos, sin = math.cos(angle), math.sin(angle)
        x = math.copysign(abs(cos) ** (2 / SQUIRCLE_EXPONENT), cos)
        y = math.copysign(abs(sin) ** (2 / SQUIRCLE_EXPONENT), sin)
        point = center + QPointF(x, y) * radius
        path.lineTo(point) if index else path.moveTo(point)
    path.closeSubpath()
    return path


def visible_rect(image: QImage) -> QRect:
    """
    Smallest rectangle with the pixels of the image that are not fully transparent (the whole image if none are).
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()
    alpha = bytes(image.constBits())[3::4]  # The pixels are stored as B, G, R, A
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        row = alpha[y * width:(y + 1) * width]
        start = width - len(row.lstrip(b'\0'))
        if start < width:
            end = len(row.rstrip(b'\0')) - 1
            left, right = min(left, start), max(right, end)
            top, bottom = min(top, y), y
    if right < 0:
        return image.rect()
    return QRect(left, top, right - left + 1, bottom - top + 1)


def macos_image(image: QImage) -> QImage:
    """
    The image on a white squircle with a soft shadow, as the icons of macOS, at the size of the image.
    """
    size = image.width()
    shape = squircle(QRectF(0, 0, size * SQUIRCLE_SIZE, size * SQUIRCLE_SIZE).translated(
        size * (1 - SQUIRCLE_SIZE) / 2, size * (1 - SQUIRCLE_SIZE) / 2))

    # Shadow: the squircle in black, blurred by scaling it down and up again
    shadow = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    shadow.fill(Qt.GlobalColor.transparent)
    painter = QPainter(shadow)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillPath(shape.translated(0, size * SHADOW_OFFSET), QColor(0, 0, 0, SHADOW_ALPHA))
    painter.end()
    small = shadow.scaled(size // SHADOW_BLUR, size // SHADOW_BLUR, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    shadow = small.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

    icon = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(0, 0, shadow)
    painter.fillPath(shape, Qt.GlobalColor.white)
    # The visible part of the image, centered in the squircle and as large as fits in the square of the content
    visible = visible_rect(image)
    scale = size * SQUIRCLE_SIZE * CONTENT_SIZE / max(visible.width(), visible.height())
    target = QRectF(0, 0, visible.width() * scale, visible.height() * scale)
    target.moveCenter(QRectF(0, 0, size, size).center())
    painter.drawImage(target, image, QRectF(visible))
    painter.end()
    return icon.convertToFormat(QImage.Format.Format_ARGB32)


def ico_data(image: QImage) -> bytes:
    """
    Windows icon file with the image in each size, stored as PNG images.
    """
    images = [png(image, size) for size in ICO_SIZES]
    header = struct.pack('<HHH', 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b''
    for size, data in zip(ICO_SIZES, images, strict=True):
        # A width and height of 0 mean 256 pixels
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b''.join(images)


def icns_data(image: QImage) -> bytes:
    """
    macOS icon file with the image (on a white squircle) in each size, stored as PNG images.
    """
    image = macos_image(image)
    content = b''
    for kind, size in ICNS_TYPES.items():
        data = png(image, size)
        content += kind + struct.pack('>I', 8 + len(data)) + data
    return b'icns' + struct.pack('>I', 8 + len(content)) + content


def make_icons(source: Path = APP_ICON_PNG):
    image = QImage(str(source))
    if image.isNull():
        raise SystemExit(f'Unable to read the image {source}')
    if image.width() != image.height() or image.width() < MIN_SIZE:
        raise SystemExit(f'The image must be square and at least {MIN_SIZE} × {MIN_SIZE} pixels '
                         f'({image.width()} × {image.height()})')

    if source.resolve() != APP_ICON_PNG.resolve():
        shutil.copyfile(source, APP_ICON_PNG)
    APP_ICON_ICNS.write_bytes(icns_data(image))
    APP_ICON_ICO.write_bytes(ico_data(image))
    for path in (APP_ICON_PNG, APP_ICON_ICNS, APP_ICON_ICO):
        print(f'Written {path}')


if __name__ == '__main__':
    make_icons(Path(sys.argv[1]) if len(sys.argv) > 1 else APP_ICON_PNG)
