import tempfile
from datetime import datetime

import pytest
from feedparser import FeedParserDict

from arxiv_sorter import pipeline
from arxiv_sorter.cli import parse_args
from arxiv_sorter.pipeline import MAX_SEARCHES, SearchFilesError, get_last_new
from arxiv_sorter.updater import Release


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Search files and abstracts folder, without update checks nor figures."""
    searches = tmp_path / 'searches'
    searches.mkdir()
    (searches / 'keywords.txt').write_text('spin qubit\n', encoding='utf-8')
    (searches / 'authors.txt').write_text('Loss\n', encoding='utf-8')
    (searches / 'categories.txt').write_text('cond-mat\n', encoding='utf-8')
    monkeypatch.setattr(pipeline, 'check_for_update', lambda *args, **kwargs: None)

    def run(*extra: str):
        args = parse_args(['-d', str(searches), '-a', str(tmp_path / 'abstracts'), '-i', '-e', *extra])
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline.run(args, tempfile.TemporaryDirectory(dir=temp_dir))

    run.searches = searches
    run.abstracts = tmp_path / 'abstracts'
    return run


class FakeArxiv:
    """Answers the requests with the given days (date -> entries), and records them."""

    def __init__(self, days: dict[datetime, list] | None = None):
        self.days = days or {}
        self.requests = []

    def __call__(self, categories, date_0, date_f):
        self.requests.append((categories, date_0.date(), date_f.date()))
        dates = sorted(self.days)
        return [self.days[date] for date in dates], dates


class TestRun:
    def test_writes_the_sorted_mailing_list(self, workspace, monkeypatch, make_entry):
        day = datetime(2026, 9, 22, 18)
        arxiv = FakeArxiv({day: [
            make_entry(arxiv_id='2609.00001v1', title='Unrelated work', authors=('Alice Smith',)),
            make_entry(arxiv_id='2609.00002v1', title='A spin qubit in germanium', authors=('Bob Jones',)),
            make_entry(arxiv_id='2609.00003v1', title='Another title', authors=('Daniel Loss',)),
        ]})
        monkeypatch.setattr(pipeline, 'search_entries', arxiv)

        workspace('--date0', '20260922', '--datef', '20260923')

        text = (workspace.abstracts / '2026-09-22.md').read_text(encoding='utf-8')
        titles = [line for line in text.splitlines() if line.startswith('Title: ')]
        assert len(titles) == 3
        assert 'spin qubit' in titles[0] and '<span' in titles[0]  # Keyword matches first, highlighted
        assert 'Another title' in titles[1]  # Then author matches
        assert 'Unrelated work' in titles[2]
        assert arxiv.requests == [(['cond-mat'], datetime(2026, 9, 22).date(), datetime(2026, 9, 23).date())]

    def test_mistakes_stop_the_run_before_requesting_arxiv(self, workspace, monkeypatch, capsys):
        (workspace.searches / 'keywords.txt').write_text('spin qubit\nspin[ qubit\n', encoding='utf-8')
        arxiv = FakeArxiv()
        monkeypatch.setattr(pipeline, 'search_entries', arxiv)

        with pytest.raises(SearchFilesError):
            workspace()

        assert arxiv.requests == []
        assert 'keywords.txt, line 2: invalid regular expression' in capsys.readouterr().out

    def test_gives_up_after_the_maximum_of_searches(self, workspace, monkeypatch, capsys):
        arxiv = FakeArxiv()  # arXiv never answers with submissions (e.g. a category that does not exist)
        monkeypatch.setattr(pipeline, 'search_entries', arxiv)

        workspace('--date0', '20260922', '--datef', '20260923')

        assert len(arxiv.requests) == MAX_SEARCHES == 10
        assert [request[2] for request in arxiv.requests[:2]] == [datetime(2026, 9, 23).date(),
                                                                  datetime(2026, 9, 22).date()]  # Going back
        assert f'No submissions found in the last {MAX_SEARCHES} requests' in capsys.readouterr().out
        assert not any(workspace.abstracts.glob('*.md'))

    def test_searches_earlier_until_something_is_found(self, workspace, monkeypatch, make_entry):
        calls = []

        def empty_twice(categories, date_0, date_f):
            calls.append(date_0)
            if len(calls) < 3:
                return [[]], [date_0]
            return [[make_entry()]], [date_0]

        monkeypatch.setattr(pipeline, 'search_entries', empty_twice)

        workspace('--date0', '20260924', '--datef', '20260925')

        assert len(calls) == 3
        assert len(list(workspace.abstracts.glob('*.md'))) == 1


def _entries(*indices: int) -> list[FeedParserDict]:
    return [FeedParserDict(index=index, last_new=False) for index in indices]


def test_marks_the_last_new_entry():
    entries = _entries(3, 1, 0, -1, -1)

    get_last_new(entries)

    assert [entry.last_new for entry in entries] == [False, False, True, False, False]


def test_nothing_marked_without_updated_entries():
    entries = _entries(3, 0)

    get_last_new(entries)

    assert not any(entry.last_new for entry in entries)


def test_nothing_marked_when_every_entry_is_updated():
    entries = _entries(-1, -1)

    get_last_new(entries)

    assert not any(entry.last_new for entry in entries)


class TestCheckUpdates:
    RELEASE = Release(version='v9.9.9', url='https://example.org/arXiv-sorter-Windows.zip',
                      asset='arXiv-sorter-Windows.zip', page='https://example.org/v9.9.9')

    @pytest.fixture
    def updates(self, monkeypatch):
        calls = []
        monkeypatch.setattr(pipeline, 'gui_mode', lambda: False)
        monkeypatch.setattr(pipeline, 'check_for_update', lambda *args, **kwargs: self.RELEASE)
        monkeypatch.setattr(pipeline, 'download_and_update', calls.append)
        monkeypatch.setattr(pipeline, 'remove_old_version', lambda: None)
        monkeypatch.setattr(pipeline.console, 'question', lambda text: True)
        return calls

    def test_binary_updated(self, updates, monkeypatch):
        monkeypatch.setattr(pipeline, 'is_frozen', lambda: True)
        pipeline._check_updates(parse_args(['-u']))
        assert updates == [self.RELEASE]

    @pytest.mark.parametrize(('argv', 'frozen'), [([], True), (['-u'], False)])
    def test_only_announced(self, updates, monkeypatch, capsys, argv, frozen):
        monkeypatch.setattr(pipeline, 'is_frozen', lambda: frozen)
        pipeline._check_updates(parse_args(argv))
        assert not updates
        assert 'A new version of arXiv-sorter is available: v9.9.9' in capsys.readouterr().out

    def test_not_checked_from_the_gui(self, monkeypatch):
        monkeypatch.setattr(pipeline, 'gui_mode', lambda: True)
        monkeypatch.setattr(pipeline, 'check_for_update', lambda *args, **kwargs: pytest.fail('checked'))
        pipeline._check_updates(parse_args([]))
