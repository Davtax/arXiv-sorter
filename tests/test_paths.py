"""Path handling: custom and space-containing directories must work end to end."""
from pathlib import Path
from types import SimpleNamespace

from app import pdf_scrapper
from app.pdf_scrapper import PDFFIGURES2_PATH, detect_figure, get_images_pdf_scrapper


def test_java_arguments_keep_space_containing_paths_intact(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_scrapper, 'run', lambda args, **kwargs: calls.append(args))
    pdf_path = tmp_path / 'pdf files'
    data_path = tmp_path / 'json files'

    detect_figure(pdf_path, data_path, 2)

    assert calls == [['java', '-jar', PDFFIGURES2_PATH, pdf_path, '-e', '-t', '2', '-d', data_path, '-q']]


def _fake_pipeline(monkeypatch):
    monkeypatch.setattr(pdf_scrapper, 'check_java', lambda: True)
    monkeypatch.setattr(pdf_scrapper, 'check_pdffigure2', lambda: True)
    monkeypatch.setattr(pdf_scrapper, 'download_pdfs', lambda *args: None)
    monkeypatch.setattr(pdf_scrapper, 'detect_figure', lambda *args: None)
    monkeypatch.setattr(pdf_scrapper, 'extract_from_json', lambda *args: True)


def test_figures_follow_custom_abstracts_directory(tmp_path, monkeypatch):
    _fake_pipeline(monkeypatch)
    abstracts_dir = tmp_path / 'custom output'
    temp_dir = SimpleNamespace(name=str(tmp_path / 'temporary files'))

    links = get_images_pdf_scrapper('2026-01-02', [SimpleNamespace(id='https://arxiv.org/abs/1234.5678')], temp_dir,
                                    abstracts_dir, separate_files=False)

    assert (abstracts_dir / 'figures' / '2026-01-02').is_dir()
    assert links == ['figures/2026-01-02/1234.5678.png']


def test_figure_links_are_relative_to_the_entry_folder_when_separated(tmp_path, monkeypatch):
    _fake_pipeline(monkeypatch)
    temp_dir = SimpleNamespace(name=str(tmp_path / 'tmp'))

    links = get_images_pdf_scrapper('2026-01-02', [SimpleNamespace(id='https://arxiv.org/abs/1234.5678')], temp_dir,
                                    tmp_path / 'abstracts', separate_files=True)

    assert links == [(Path('..') / 'figures' / '2026-01-02' / '1234.5678.png').as_posix()]


def test_without_java_no_figures_are_linked(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_scrapper, 'check_java', lambda: False)
    temp_dir = SimpleNamespace(name=str(tmp_path / 'tmp'))
    entries = [SimpleNamespace(id='https://arxiv.org/abs/1'), SimpleNamespace(id='https://arxiv.org/abs/2')]

    assert get_images_pdf_scrapper('2026-01-02', entries, temp_dir, tmp_path / 'abstracts', False) == [None, None]
