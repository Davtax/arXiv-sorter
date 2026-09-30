import json
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from types import SimpleNamespace

import pytest

from arxorter import figures
from arxorter.figures import clean_previous_figures, extract_all, extract_from_json


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



def write_figure_json(folder, id_entry, fig_type='Figure'):
    data = [{'figType': fig_type, 'page': 0, 'regionBoundary': {'x1': 0, 'x2': 9, 'y1': 0, 'y2': 9}}]
    (folder / f'{id_entry}.json').write_text(json.dumps(data), encoding='utf-8')


class TestExtractAll:
    IDS = ['2609.00001', '2609.00002', '2609.00003', '2609.00004']

    def test_one_thread_extracts_in_this_process(self, tmp_path, monkeypatch):
        monkeypatch.setattr(figures, 'ProcessPoolExecutor', None)  # Never started
        monkeypatch.setattr(figures, 'extract_from_json', lambda id_entry, *folders: id_entry.endswith(('1', '3')))

        assert extract_all(self.IDS, tmp_path, tmp_path, tmp_path, threads=1) == [True, False, True, False]

    def test_several_threads_extract_in_other_processes(self, tmp_path, capsys, verbose):
        """Real processes, which report the figures found in the order of the entries, and their details."""
        write_figure_json(tmp_path, self.IDS[0], fig_type='Table')
        write_figure_json(tmp_path, self.IDS[1], fig_type='Table')
        (tmp_path / f'{self.IDS[2]}.json').write_text('{not json', encoding='utf-8')

        assert extract_all(self.IDS, tmp_path, tmp_path, tmp_path, threads=3) == [False] * 4
        assert f'Unable to read the figures detected in {self.IDS[2]}' in capsys.readouterr().out

    def test_a_crashed_process_leaves_the_other_figures(self, tmp_path, capsys, monkeypatch):
        class CrashingPool:
            """Pool whose second task crashes its process."""
            def __init__(self, workers):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def submit(self, function, id_entry, *folders):
                future = Future()
                if id_entry == TestExtractAll.IDS[1]:
                    future.set_exception(BrokenProcessPool('A process terminated abruptly'))
                else:
                    future.set_result((True, ''))
                return future

        monkeypatch.setattr(figures, 'ProcessPoolExecutor', CrashingPool)
        found = extract_all(self.IDS, tmp_path, tmp_path, tmp_path, threads=4)

        assert found[1] is False
        assert self.IDS[1] in capsys.readouterr().out


class TestCheckPdffigures2:
    @pytest.fixture
    def jar(self, tmp_path, monkeypatch):
        path = tmp_path / 'config' / 'pdffigures2.jar'
        monkeypatch.setattr(figures, 'PDFFIGURES2_PATH', path)
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
