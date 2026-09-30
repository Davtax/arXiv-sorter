"""Path handling: custom and space-containing directories must work end to end."""
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from arxorter import console, figures
from arxorter.figures import PDFFIGURES2_PATH, detect_figure, extract_figures
from arxorter.protocol import PROGRESS_TAG


class FakePdffigures2:
    """Stand-in for the pdffigures2 process: each poll writes the JSON file of the next PDF."""
    calls = []

    def __init__(self, args, **kwargs):
        self.calls.append(args)
        self.pdfs = sorted(Path(args[3]).glob('*.pdf'))
        self.json_folder = Path(args[8])
        self.skip = set()  # PDFs without a JSON file (e.g. not readable)

    def poll(self):
        if not self.pdfs:
            return 0
        pdf = self.pdfs.pop(0)
        if pdf.stem not in self.skip:
            (self.json_folder / f'{pdf.stem}.json').write_text('[]')
        return None

    def wait(self):
        return 0


def test_java_arguments_keep_space_containing_paths_intact(tmp_path, monkeypatch):
    FakePdffigures2.calls = []
    monkeypatch.setattr(figures, 'Popen', FakePdffigures2)
    pdf_path = tmp_path / 'pdf files'
    pdf_path.mkdir()
    data_path = tmp_path / 'json files'

    java = tmp_path / 'java runtime' / 'java'

    detect_figure(pdf_path, data_path, 2, java)

    assert FakePdffigures2.calls == [
        [java, '-jar', PDFFIGURES2_PATH, pdf_path, '-e', '-t', '2', '-d', str(data_path) + os.sep, '-q']]


class TestDetectionProgress:
    @pytest.fixture
    def pdfs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(console, 'GUI_MODE', True)  # Progress as tagged lines, easy to check
        folder = tmp_path / 'pdfs'
        folder.mkdir()
        for name in ('a', 'b', 'c'):
            (folder / f'{name}.pdf').write_bytes(b'%PDF')
        return folder

    @staticmethod
    def progress(output: str) -> list[str]:
        return [line.removeprefix(PROGRESS_TAG) for line in output.splitlines() if line.startswith(PROGRESS_TAG)]

    def test_counts_the_json_files_written(self, pdfs, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(figures, 'Popen', FakePdffigures2)

        detect_figure(pdfs, tmp_path / 'data', 1, t_poll=0)

        assert self.progress(capsys.readouterr().out) == [f'{n}\t3\tDetecting figures' for n in (1, 2, 3)]

    def test_completes_when_some_pdfs_have_no_json(self, pdfs, tmp_path, monkeypatch, capsys):
        def without_b(args, **kwargs):
            process = FakePdffigures2(args, **kwargs)
            process.skip = {'b'}
            return process

        monkeypatch.setattr(figures, 'Popen', without_b)

        detect_figure(pdfs, tmp_path / 'data', 1, t_poll=0)

        assert self.progress(capsys.readouterr().out)[-1] == '3\t3\tDetecting figures'

    def test_no_progress_bar_without_pdfs(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(console, 'GUI_MODE', True)
        monkeypatch.setattr(figures, 'Popen', FakePdffigures2)
        (tmp_path / 'pdfs').mkdir()

        detect_figure(tmp_path / 'pdfs', tmp_path / 'data', 1, t_poll=0)

        assert self.progress(capsys.readouterr().out) == []


def _fake_pipeline(monkeypatch):
    monkeypatch.setattr(figures, 'find_java', lambda: 'java')
    monkeypatch.setattr(figures, 'check_pdffigure2', lambda: True)
    monkeypatch.setattr(figures, 'download_pdfs', lambda *args: None)
    monkeypatch.setattr(figures, 'detect_figure', lambda *args: None)
    monkeypatch.setattr(figures, 'extract_from_json', lambda *args: True)


def test_figures_follow_custom_abstracts_directory(tmp_path, monkeypatch):
    _fake_pipeline(monkeypatch)
    abstracts_dir = tmp_path / 'custom output'
    temp_dir = SimpleNamespace(name=str(tmp_path / 'temporary files'))

    links = extract_figures('2026-01-02', [SimpleNamespace(id='https://arxiv.org/abs/1234.5678')], temp_dir,
                                    abstracts_dir, separate_files=False)

    assert (abstracts_dir / 'figures' / '2026-01-02').is_dir()
    assert links == ['figures/2026-01-02/1234.5678.png']


def test_figure_links_are_relative_to_the_entry_folder_when_separated(tmp_path, monkeypatch):
    _fake_pipeline(monkeypatch)
    temp_dir = SimpleNamespace(name=str(tmp_path / 'tmp'))

    links = extract_figures('2026-01-02', [SimpleNamespace(id='https://arxiv.org/abs/1234.5678')], temp_dir,
                                    tmp_path / 'abstracts', separate_files=True)

    assert links == [(Path('..') / 'figures' / '2026-01-02' / '1234.5678.png').as_posix()]


def test_without_java_no_figures_are_linked(tmp_path, monkeypatch):
    monkeypatch.setattr(figures, 'find_java', lambda: None)
    temp_dir = SimpleNamespace(name=str(tmp_path / 'tmp'))
    entries = [SimpleNamespace(id='https://arxiv.org/abs/1'), SimpleNamespace(id='https://arxiv.org/abs/2')]

    assert extract_figures('2026-01-02', entries, temp_dir, tmp_path / 'abstracts', False) == [None, None]


class TestRemoveFolder:
    def test_retries_while_locked(self, tmp_path, monkeypatch):
        folder = tmp_path / 'figures'
        folder.mkdir()
        real_rmtree = shutil.rmtree
        calls = []

        def locked_once(path, **kwargs):
            calls.append(path)
            if len(calls) == 1:
                raise PermissionError('locked')
            real_rmtree(path, **kwargs)

        monkeypatch.setattr(figures.shutil, 'rmtree', locked_once)

        assert figures.remove_folder(folder, t_sleep=0)
        assert len(calls) == 2 and not folder.exists()

    def test_gives_up_with_message(self, tmp_path, monkeypatch, capsys):
        def always_locked(path, **kwargs):
            raise PermissionError('locked')

        monkeypatch.setattr(figures.shutil, 'rmtree', always_locked)

        assert not figures.remove_folder(tmp_path, retries=2, t_sleep=0)
        assert 'Permission error deleting' in capsys.readouterr().out


def test_threads_are_passed_to_pdffigures2(tmp_path, monkeypatch):
    _fake_pipeline(monkeypatch)
    calls = []
    monkeypatch.setattr(figures, 'detect_figure', lambda pdf_folder, json_folder, threads, java: calls.append(threads))
    temp_dir = SimpleNamespace(name=str(tmp_path / 'tmp'))

    extract_figures('2026-01-02', [SimpleNamespace(id='https://arxiv.org/abs/1')], temp_dir, tmp_path / 'abstracts',
                    False, threads=3)

    assert calls == [3]
