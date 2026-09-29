import os
import sys

import pytest

# Linux CI runners have no display. Elsewhere the real platform is used, so the tests run with its native style
if sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtGui = pytest.importorskip('PySide6.QtGui')

from arxiv_sorter.gui.theme import apply_theme, is_dark  # noqa: E402

ACTIVE, INACTIVE = QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorGroup.Inactive
ROLES = (QtGui.QPalette.ColorRole.Accent, QtGui.QPalette.ColorRole.Highlight, QtGui.QPalette.ColorRole.Button)


@pytest.fixture(scope='module')
def app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    apply_theme(app, 'system')


@pytest.mark.skipif(sys.platform == 'darwin', reason='The macOS style greys the highlight of inactive windows')
@pytest.mark.parametrize('sequence', [('light', 'dark'), ('dark', 'light'), ('light', 'dark', 'light', 'system')])
def test_ticks_keep_their_highlight_without_focus(app, sequence):
    """
    After switching from light to dark, the Windows 11 style used to draw the ticks of inactive windows with the
    background color. Inactive widgets must use the same highlight colors as active ones.
    """
    widgets = [QtWidgets.QCheckBox('check'), QtWidgets.QRadioButton('radio')]

    for theme in sequence:
        apply_theme(app, theme)

    for widget in widgets:
        palette = widget.palette()
        assert [palette.color(INACTIVE, role).name() for role in ROLES] == [
            palette.color(ACTIVE, role).name() for role in ROLES], type(widget).__name__


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_theme_is_applied(app, theme):
    apply_theme(app, theme)

    assert is_dark(app.palette()) == (theme == 'dark')
