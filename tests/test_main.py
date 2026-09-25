from feedparser import FeedParserDict

from app.main import get_last_new


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
