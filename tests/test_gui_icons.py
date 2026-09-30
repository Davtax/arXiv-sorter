import importlib.util
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage, QImageReader

from arxorter.gui import icons

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope='module')
def make_icons():
    spec = importlib.util.spec_from_file_location('make_icons', ROOT / 'scripts' / 'make_icons.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def icon_dir(tmp_path, make_icons, monkeypatch):
    """
    Icon files written by the script in a temporary folder, instead of the ones of the program.
    """
    for name in ('APP_ICON_PNG', 'APP_ICON_ICNS', 'APP_ICON_ICO'):
        monkeypatch.setattr(make_icons, name, tmp_path / getattr(icons, name).name)
    return tmp_path


def read_images(path: Path) -> list[QImage]:
    reader = QImageReader(str(path))
    images = []
    for _ in range(reader.imageCount()):
        images.append(reader.read())
        reader.jumpToNextImage()
    return images


def icns_images(path: Path) -> dict[bytes, int]:
    """
    Type and width of each image of an .icns file.
    """
    data = path.read_bytes()
    assert data[:4] == b'icns' and struct.unpack('>I', data[4:8])[0] == len(data)
    offset, found = 8, {}
    while offset < len(data):
        kind, length = data[offset:offset + 4], struct.unpack('>I', data[offset + 4:offset + 8])[0]
        found[kind] = QImage.fromData(data[offset + 8:offset + length], 'PNG').width()
        offset += length
    return found


class TestIconFilesOfTheProgram:
    def test_png_is_large_and_square(self):
        image = QImage(str(icons.APP_ICON_PNG))
        assert image.width() == image.height() >= 1024

    def test_app_icon_is_the_png(self, qapp):
        assert not icons.app_icon().isNull()

    def test_icns(self, make_icons):
        assert icns_images(icons.APP_ICON_ICNS) == make_icons.ICNS_TYPES

    def test_ico(self, make_icons):
        assert sorted(image.width() for image in read_images(icons.APP_ICON_ICO)) == list(make_icons.ICO_SIZES)

    @pytest.mark.skipif(sys.platform != 'darwin', reason='iconutil of macOS')
    def test_icns_read_by_macos(self, tmp_path):
        iconset = tmp_path / 'icon.iconset'
        subprocess.run(['iconutil', '-c', 'iconset', str(icons.APP_ICON_ICNS), '-o', str(iconset)], check=True)
        assert (iconset / 'icon_512x512@2x.png').is_file()


class TestMakeIcons:
    def test_files_made_from_a_new_image(self, make_icons, icon_dir, tmp_path, capsys):
        new = tmp_path / 'new.png'
        image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
        image.fill(0xff2060c0)
        image.save(str(new))

        make_icons.make_icons(new)

        assert QImage(str(icon_dir / 'arxorter.png')) == QImage(str(new))
        assert icns_images(icon_dir / 'arxorter.icns') == make_icons.ICNS_TYPES
        ico = read_images(icon_dir / 'arxorter.ico')
        assert sorted(image.width() for image in ico) == list(make_icons.ICO_SIZES)
        assert ico[0].pixelColor(8, 8).name() == '#2060c0'  # Scaled from the new image
        assert capsys.readouterr().out.count('Written') == 3

    def test_macos_icon_is_on_a_white_squircle(self, make_icons, icon_dir, tmp_path):
        new = tmp_path / 'new.png'
        image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
        image.fill(0)  # Transparent, with a blue rectangle in the middle
        for x in range(400, 600):
            for y in range(450, 550):
                image.setPixelColor(x, y, QColor('#2060c0'))
        image.save(str(new))

        make_icons.make_icons(new)

        data = (icon_dir / 'arxorter.icns').read_bytes()
        start = data.index(b'ic10') + 8
        icon = QImage.fromData(data[start:start + struct.unpack('>I', data[start - 4:start])[0] - 8], 'PNG')
        assert icon.pixelColor(10, 10).alpha() == 0  # Outside the squircle
        assert icon.pixelColor(512, 130).name() == '#ffffff'  # Inside the squircle, around the image
        assert icon.pixelColor(512, 512).name() == '#2060c0'  # The visible part of the image, enlarged
        assert icon.pixelColor(200, 512).name() == '#2060c0'
        assert QImage(str(icon_dir / 'arxorter.png')).pixelColor(200, 512).alpha() == 0  # Only on macOS

    def test_visible_rect(self, make_icons):
        image = QImage(64, 64, QImage.Format.Format_ARGB32)
        image.fill(0)
        assert make_icons.visible_rect(image) == image.rect()  # Nothing visible
        image.setPixelColor(10, 20, QColor('red'))
        image.setPixelColor(30, 5, QColor('red'))
        assert make_icons.visible_rect(image).getCoords() == (10, 5, 30, 20)

    @pytest.mark.parametrize('width, height', [(512, 512), (1024, 800)])
    def test_image_too_small_or_not_square(self, make_icons, icon_dir, tmp_path, width, height):
        new = tmp_path / 'new.png'
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(0xff000000)
        image.save(str(new))

        with pytest.raises(SystemExit, match='square and at least 1024'):
            make_icons.make_icons(new)
        assert not (icon_dir / 'arxorter.png').exists()

    def test_not_an_image(self, make_icons, icon_dir, tmp_path):
        new = tmp_path / 'new.png'
        new.write_text('not an image')
        with pytest.raises(SystemExit, match='Unable to read'):
            make_icons.make_icons(new)
