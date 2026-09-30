"""
Make the icon files of arXiv-sorter from a square PNG image of at least 1024 × 1024 pixels (e.g. exported from
logo/arxiv-sorter-icon.af). The image replaces the PNG of the application icon, and the .icns (macOS app) and .ico
(Windows executable) files next to it are made from it, all in src/arxiv_sorter/gui/app-icon.

Usage: python scripts/make_icons.py [path to the PNG image]
Without an image, the icon files are made again from the current PNG.
"""
import shutil
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

from arxiv_sorter.gui.icons import APP_ICON_ICNS, APP_ICON_ICO, APP_ICON_PNG

MIN_SIZE = 1024  # pixels, the largest image of the .icns file
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)  # Windows, up to 256 pixels
# macOS: type of each image in the .icns file and its size in pixels (the @2x types are for Retina displays)
ICNS_TYPES = {b'icp4': 16, b'icp5': 32, b'icp6': 64, b'ic07': 128, b'ic08': 256, b'ic09': 512, b'ic10': 1024,
              b'ic11': 32, b'ic12': 64, b'ic13': 256, b'ic14': 512}


def png(image: QImage, size: int) -> bytes:
    """
    The image scaled to the size, as a PNG file.
    """
    scaled = image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    scaled.save(buffer, 'PNG')
    return bytes(buffer.data())


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
    macOS icon file with the image in each size, stored as PNG images.
    """
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
