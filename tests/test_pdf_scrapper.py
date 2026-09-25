import json

from app import pdf_scrapper
from app.pdf_scrapper import clean_previous_figures, extract_from_json


class TestExtractFromJson:
    def test_missing_json(self, tmp_path):
        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is False

    def test_invalid_json(self, tmp_path, capsys):
        (tmp_path / '1234.5678.json').write_text('{not json', encoding='utf-8')

        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is False
        assert 'Error decoding' in capsys.readouterr().out

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
        monkeypatch.setattr(pdf_scrapper, '_extract_region',
                            lambda id_entry, pdf, image, json_entry: extracted.append(json_entry))

        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is True
        assert extracted == [region(0, 1, 3)]

    def test_skips_figures_outside_the_page(self, tmp_path, monkeypatch):
        figure = {'figType': 'Figure', 'page': 0, 'regionBoundary': {'x1': 0, 'x2': 1, 'y1': 0, 'y2': 1}}
        (tmp_path / '1234.5678.json').write_text(json.dumps([figure]), encoding='utf-8')

        def out_of_page(*args):
            raise ValueError('rect not in mediabox')

        monkeypatch.setattr(pdf_scrapper, '_extract_region', out_of_page)

        assert extract_from_json('1234.5678', tmp_path, tmp_path, tmp_path) is False


def test_clean_previous_figures_removes_orphans_only(tmp_path):
    figures = tmp_path / 'figures'
    for name in ('2026-01-01', '2026-01-02', '2026-01-03'):
        (figures / name).mkdir(parents=True)
    (tmp_path / '2026-01-01.md').touch()  # joined markdown file
    (tmp_path / '2026-01-02').mkdir()  # separated markdown folder

    clean_previous_figures(tmp_path)

    assert sorted(path.name for path in figures.iterdir()) == ['2026-01-01', '2026-01-02']
