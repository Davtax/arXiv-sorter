import io

import pytest

from arxiv_sorter import console
from arxiv_sorter.console import Progressbar, question
from arxiv_sorter.protocol import PROGRESS_TAG, QUESTION_TAG, WRITTEN_TAG


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


def test_progressbar_reports_progress():
    out = io.StringIO()
    pbar = Progressbar(4, prefix='Work', out=out)

    pbar.update(2)
    pbar.update(2)
    pbar.close()

    text = out.getvalue()
    assert 'Work[' in text
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
