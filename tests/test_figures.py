import json
from types import SimpleNamespace

import pytest

from arxiv_sorter import figures
from arxiv_sorter.figures import clean_previous_figures, extract_from_json


class TestExtractFromJson:
    def test_missing_json(self, tmp_path):
        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is False

    def test_invalid_json(self, tmp_path, capsys, verbose):
        (tmp_path / '1234.5678.json').write_text('{not json', encoding='utf-8')

        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is False
        assert 'Unable to read the figures detected in 1234.5678' in capsys.readouterr().out

    def test_only_tables(self, tmp_path):
        data = [{'figType': 'Table', 'page': 0, 'regionBoundary': {'x1': 0, 'x2': 1, 'y1': 0, 'y2': 1}}]
        (tmp_path / '1234.5678.json').write_text(json.dumps(data), encoding='utf-8')

        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is False

    def test_extracts_first_figure_in_reading_order(self, tmp_path, monkeypatch):
        def region(page, x1, y1):
            return {'figType': 'Figure', 'page': page, 'regionBoundary': {'x1': x1, 'x2': 9, 'y1': y1, 'y2': 9}}

        data = [region(1, 0, 0), region(0, 5, 0), region(0, 1, 3)]
        (tmp_path / '1234.5678.json').write_text(json.dumps(data), encoding='utf-8')
        extracted = []
        monkeypatch.setattr(figures, '_extract_region',
                            lambda id_entry, pdf, image, json_entry: extracted.append(json_entry))

        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is True
        assert extracted == [region(0, 1, 3)]

    def test_skips_figures_outside_the_page(self, tmp_path, monkeypatch):
        figure = {'figType': 'Figure', 'page': 0, 'regionBoundary': {'x1': 0, 'x2': 1, 'y1': 0, 'y2': 1}}
        (tmp_path / '1234.5678.json').write_text(json.dumps([figure]), encoding='utf-8')

        def out_of_page(*args):
            raise ValueError('rect not in mediabox')

        monkeypatch.setattr(figures, '_extract_region', out_of_page)

        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is False


def test_clean_previous_figures_removes_orphans_only(tmp_path):
    figures = tmp_path / 'figures'
    for name in ('2026-01-01', '2026-01-02', '2026-01-03'):
        (figures / name).mkdir(parents=True)
    (tmp_path / '2026-01-01.md').touch()  # joined markdown file
    (tmp_path / '2026-01-02').mkdir()  # separated markdown folder

    clean_previous_figures(tmp_path)

    assert sorted(path.name for path in figures.iterdir()) == ['2026-01-01', '2026-01-02']


class TestCheckPdffigures2:
    @pytest.fixture
    def jar(self, tmp_path, monkeypatch):
        path = tmp_path / 'config' / 'pdffigures2.jar'
        monkeypatch.setattr(figures, 'PDFFIGURES2_PATH', path)
        monkeypatch.setattr(figures, 'LEGACY_PDFFIGURES2_PATH', tmp_path / 'program' / '.arXiv_sorter' / 'old.jar')
        return path

    def test_existing_jar_is_not_downloaded(self, jar, monkeypatch):
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b'jar')
        monkeypatch.setattr(figures.requests, 'get', lambda *args, **kwargs: pytest.fail('downloaded'))

        assert figures.check_pdffigure2()

    def test_missing_jar_is_downloaded_and_kept(self, jar, monkeypatch, capsys):
        response = SimpleNamespace(content=b'jar', raise_for_status=lambda: None)
        monkeypatch.setattr(figures.requests, 'get', lambda *args, **kwargs: response)

        assert figures.check_pdffigure2()
        assert jar.read_bytes() == b'jar'
        output = capsys.readouterr().out
        assert 'only needed the first time' in output and 'saved in' in output

    def test_jar_of_previous_versions_is_copied(self, jar, monkeypatch, capsys):
        figures.LEGACY_PDFFIGURES2_PATH.parent.mkdir(parents=True)
        figures.LEGACY_PDFFIGURES2_PATH.write_bytes(b'old jar')
        monkeypatch.setattr(figures.requests, 'get', lambda *args, **kwargs: pytest.fail('downloaded'))

        assert figures.check_pdffigure2()
        assert jar.read_bytes() == b'old jar'
        assert figures.LEGACY_PDFFIGURES2_PATH.exists()  # Left in place, previous versions may still use it
        assert 'copied from' in capsys.readouterr().out

    def test_no_partial_file_is_left(self, jar, monkeypatch):
        response = SimpleNamespace(content=b'jar', raise_for_status=lambda: None)
        monkeypatch.setattr(figures.requests, 'get', lambda *args, **kwargs: response)

        figures.check_pdffigure2()

        assert sorted(path.name for path in jar.parent.iterdir()) == [jar.name]

    def test_failed_download_disables_figures(self, jar, monkeypatch, capsys):
        def offline(*args, **kwargs):
            raise figures.requests.ConnectionError('offline')

        monkeypatch.setattr(figures.requests, 'get', offline)

        assert not figures.check_pdffigure2()
        assert not jar.exists()
        assert 'Running without figure detection' in capsys.readouterr().out
