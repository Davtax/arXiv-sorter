from types import SimpleNamespace

from arxiv_sorter.network import get_image


class TestGetImage:
    def test_no_response(self):
        assert get_image(None) == ''

    def test_page_without_png(self):
        assert get_image(SimpleNamespace(text='<html><img src="x.jpg"></html>')) == ''

    def test_first_png_source(self):
        html = '<p><img class="ltx" src="x1.png" alt="Fig 1"></p><img src="x2.png">'
        assert get_image(SimpleNamespace(text=html)) == 'x1.png'
