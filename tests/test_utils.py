import io
from types import SimpleNamespace

import pytest

from app.utils import Progressbar, get_image, question


class TestGetImage:
    def test_no_response(self):
        assert get_image(None) == ''

    def test_page_without_png(self):
        assert get_image(SimpleNamespace(text='<html><img src="x.jpg"></html>')) == ''

    def test_first_png_source(self):
        html = '<p><img class="ltx" src="x1.png" alt="Fig 1"></p><img src="x2.png">'
        assert get_image(SimpleNamespace(text=html)) == 'x1.png'


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
