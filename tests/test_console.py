import io

import pytest

from arxorter import console
from arxorter.console import Progressbar, question
from arxorter.protocol import LOG_TAG, PROGRESS_TAG, QUESTION_TAG, WRITTEN_TAG


class TestQuestion:
    @pytest.mark.parametrize(('answer', 'expected'), [('y', True), ('Y', True), ('', True), ('n', False)])
    def test_valid_answers(self, monkeypatch, answer, expected):
        monkeypatch.setattr('builtins.input', lambda _: answer)
        assert question('Continue?') is expected

    def test_repeats_until_valid_answer(self, monkeypatch, capsys):
        answers = iter(['maybe', 'n'])
        monkeypatch.setattr('builtins.input', lambda _: next(answers))

        assert question('Continue?') is False
        assert "didn't understand" in capsys.readouterr().out


class TestMessages:
    def test_icon_before_the_text(self, capsys):
        console.info('103 entries', icon='📄')

        assert capsys.readouterr().out == '📄 103 entries\n'

    @pytest.mark.parametrize(('function', 'icon'), [(console.success, '✅'), (console.warning, '⚠️'),
                                                     (console.error, '❌')])
    def test_default_icon_of_the_level(self, capsys, function, icon):
        function('text')

        assert capsys.readouterr().out == f'{icon} text\n'

    def test_step_is_separated_from_the_previous_stage(self, capsys):
        console.step('Mailing list', icon='📅')

        assert capsys.readouterr().out == '\n📅 Mailing list\n'

    def test_details_only_when_verbose(self, capsys, monkeypatch):
        console.detail('hidden')
        monkeypatch.setattr(console, 'VERBOSE', True)
        console.detail('shown')

        assert capsys.readouterr().out == '   shown\n'

    def test_multiline_text_has_a_single_icon(self, capsys):
        console.error('first\nsecond')

        assert capsys.readouterr().out == '❌ first\nsecond\n'

    def test_plain_style_has_no_icons(self, capsys, monkeypatch):
        monkeypatch.setattr(console, 'STYLE', console.Style(icons=False, colors=False))

        console.info('text', icon='📄')

        assert capsys.readouterr().out == 'text\n'

    def test_colors(self, capsys, monkeypatch):
        monkeypatch.setattr(console, 'STYLE', console.Style(icons=False, colors=True))

        console.error('text')

        assert capsys.readouterr().out == '\033[1;31mtext\033[0m\n'

    def test_gui_receives_level_icon_and_text(self, capsys, monkeypatch):
        monkeypatch.setattr(console, 'GUI_MODE', True)

        console.warning('first\nsecond', icon='🔄')

        assert capsys.readouterr().out == f'{LOG_TAG}warning\t🔄\tfirst\n{LOG_TAG}warning\t🔄\tsecond\n'


class FakeStream:
    def __init__(self, tty: bool):
        self.tty = tty

    def isatty(self):
        return self.tty


class TestDetectStyle:
    @pytest.mark.parametrize(('tty', 'environment', 'platform', 'expected'), [
        (True, {}, 'linux', console.Style(icons=True, colors=True)),
        (False, {}, 'linux', console.Style(icons=True, colors=False)),  # Redirected to a file
        (True, {'NO_COLOR': ''}, 'darwin', console.Style(icons=True, colors=False)),
        (True, {'TERM': 'dumb'}, 'linux', console.Style(icons=True, colors=False)),
        (True, {}, 'win32', console.Style(icons=False, colors=True)),  # Old Windows console
        (True, {'WT_SESSION': 'id'}, 'win32', console.Style(icons=True, colors=True)),  # Windows Terminal
        (False, {}, 'win32', console.Style(icons=True, colors=False)),  # Piped, e.g. to the GUI or a log file
        (True, {'ARXORTER_PLAIN': '1'}, 'linux', console.Style(icons=False, colors=False)),
    ])
    def test_terminals(self, tty, environment, platform, expected):
        assert console.detect_style(FakeStream(tty), environment, platform) == expected


def test_progressbar_reports_progress():
    out = io.StringIO()
    pbar = Progressbar(4, prefix='Work', out=out)

    pbar.update(2)
    pbar.update(2)
    pbar.close()

    text = out.getvalue()
    assert 'Work  ███' in text
    assert '░' in text  # Half full at 2/4
    assert '2/4' in text
    assert '4/4' in text
    assert text.endswith('\n')


class TestGuiMode:
    def test_progressbar_sends_tagged_lines(self, monkeypatch):
        monkeypatch.setattr(console, 'GUI_MODE', True)
        out = io.StringIO()

        pbar = console.Progressbar(4, prefix='Work', out=out)
        pbar.update(3)
        pbar.close()

        assert out.getvalue() == f'{PROGRESS_TAG}3\t4\tWork\n'

    def test_question_sends_tagged_line(self, monkeypatch, capsys):
        monkeypatch.setattr(console, 'GUI_MODE', True)
        monkeypatch.setattr('builtins.input', lambda *args: 'n')

        assert console.question('Update?') is False
        assert capsys.readouterr().out == f'{QUESTION_TAG}Update?\n'

    def test_written_file_sends_tagged_line(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(console, 'GUI_MODE', True)

        console.report_written(tmp_path / '2026-09-24.md', 103, 101)

        assert capsys.readouterr().out == f'{WRITTEN_TAG}103\t101\t{tmp_path / "2026-09-24.md"}\n'

    def test_written_file_is_silent_in_the_terminal(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(console, 'GUI_MODE', False)

        console.report_written(tmp_path / '2026-09-24.md', 103, 101)

        assert capsys.readouterr().out == ''
