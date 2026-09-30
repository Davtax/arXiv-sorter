import html
import os
import sys
from pathlib import Path

import pytest

# Linux CI runners have no display. Elsewhere the real platform is used, so the tests run with its native style
if sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtCore = pytest.importorskip('PySide6.QtCore')
QtGui = pytest.importorskip('PySide6.QtGui')

from arxiv_sorter.gui import log_view as log_view_module  # noqa: E402
from arxiv_sorter.gui.log_view import COLORS, LogView, linkify  # noqa: E402
from arxiv_sorter.gui.theme import dark_palette  # noqa: E402


def light_palette():
    palette = dark_palette()
    for role in (palette.ColorRole.Base, palette.ColorRole.Window):
        palette.setColor(role, QtGui.QColor('#ffffff'))
    for role in (palette.ColorRole.Text, palette.ColorRole.WindowText):
        palette.setColor(role, QtGui.QColor('#000000'))
    return palette
from arxiv_sorter.gui.summary import Outcome, WrittenFile, final_message  # noqa: E402
from arxiv_sorter.protocol import Level  # noqa: E402


@pytest.fixture(scope='module')
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class TestLinkify:
    def test_escapes_html(self):
        assert linkify('a <b> & c') == 'a &lt;b&gt; &amp; c'

    def test_links_without_trailing_punctuation(self):
        assert linkify('Install it from https://adoptium.net.') == (
            'Install it from <a href="https://adoptium.net">https://adoptium.net</a>.')


class TestPathLinks:
    def test_path_with_spaces_without_the_rest_of_the_sentence(self, tmp_path):
        folder = tmp_path / 'my abstracts'
        folder.mkdir()

        result = linkify(f'Abstracts are saved in {folder}. Done')

        assert result.startswith('Abstracts are saved in <a href="')
        assert result.endswith(f'>{html.escape(str(folder))}</a>. Done')

    def test_path_in_quotes(self, tmp_path):
        script = tmp_path / 'run.py'
        script.touch()

        assert f'>{html.escape(str(script))}</a>&quot;, line 12' in linkify(f'File "{script}", line 12, in main')

    def test_paths_that_do_not_exist_are_not_links(self, tmp_path):
        assert '<a' not in linkify(f'Missing {tmp_path / "nothing here"} and 3 / 4 and and/or')

    def test_programs_open_their_folder(self, monkeypatch, tmp_path):
        opened = []
        monkeypatch.setattr(log_view_module.QDesktopServices, 'openUrl', opened.append)
        program = tmp_path / 'python.exe'
        note = tmp_path / '2026-09-22.md'

        LogView.open_link(QtCore.QUrl.fromLocalFile(str(program)))
        LogView.open_link(QtCore.QUrl.fromLocalFile(str(note)))

        assert [Path(url.toLocalFile()) for url in opened] == [tmp_path, note]


class TestLogView:
    def test_messages_keep_their_text(self, app):
        view = LogView()

        view.add_message(Level.STEP, 'Mailing list of Tue 22 Sep 2026', '📅')
        view.add_message(Level.WARNING, 'Careful <here>', '⚠️')
        view.add_plain('Traceback (most recent call last):')

        text = view.toPlainText()
        assert '📅 Mailing list of Tue 22 Sep 2026' in text
        assert '⚠️ Careful <here>' in text
        assert 'Traceback (most recent call last):' in text

    def test_redrawn_with_the_colors_of_the_new_theme(self, app):
        view = LogView()
        view.setPalette(dark_palette())
        view.add_message(Level.ERROR, 'Broken', '❌')
        view.add_plain('raw output')
        dark_html = view.toHtml()

        view.setPalette(light_palette())

        assert view.toPlainText().count('Broken') == 1  # Same content, not duplicated
        assert 'raw output' in view.toPlainText()
        assert COLORS[True][Level.ERROR] in dark_html
        assert COLORS[False][Level.ERROR] in view.toHtml()

    def test_clear_forgets_the_messages(self, app):
        view = LogView()
        view.add_message(Level.INFO, 'old')

        view.clear()
        view.redraw()

        assert 'old' not in view.toPlainText()

    def test_paths_in_the_output_are_links(self, app, tmp_path):
        view = LogView()

        view.add_plain(f'  File "{tmp_path}", line 1')

        assert Path(tmp_path).as_posix() in view.toHtml()

    def test_summary_links_the_files(self, app, tmp_path):
        view = LogView()
        written = [WrittenFile(tmp_path / '2026-09-22.md', 103, 101)]

        view.add_summary(final_message(Outcome.FINISHED, 5, written))

        html = view.toHtml()
        assert 'Done in 5 s: 1 mailing list sorted.' in view.toPlainText()
        assert Path(tmp_path / '2026-09-22.md').as_posix() in html  # Link to the file
