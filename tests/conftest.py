import logging
from collections.abc import Callable

import pytest
from feedparser import FeedParserDict

from arxiv_sorter import console, log_file


def _make_entry(
    arxiv_id: str = '2609.01234v1',
    title: str = 'A title',
    summary: str = 'An abstract.',
    authors: tuple[str, ...] = ('Alice Smith',),
    published: str = '2026-09-24T17:00:00Z',
    updated: str | None = None,
) -> FeedParserDict:
    """Build an entry shaped like the ones returned by feedparser for the arXiv API."""
    return FeedParserDict(
        id=f'http://arxiv.org/abs/{arxiv_id}',
        title=title,
        summary=summary,
        authors=[FeedParserDict(name=name) for name in authors],
        published=published,
        updated=updated if updated is not None else published,
    )


@pytest.fixture
def make_entry() -> Callable[..., FeedParserDict]:
    return _make_entry


@pytest.fixture
def verbose(monkeypatch):
    """Show the messages that are only printed with --verbose."""
    monkeypatch.setattr(console, 'VERBOSE', True)


@pytest.fixture(autouse=True)
def logs_in_tmp(tmp_path, monkeypatch):
    """Log files of the tests are written in a temporary folder, never in the configuration folder of the user."""
    monkeypatch.setattr(log_file, 'logs_dir', lambda: tmp_path / 'logs')
    yield
    for handler in [handler for handler in log_file.LOGGER.handlers if isinstance(handler, logging.FileHandler)]:
        log_file.LOGGER.removeHandler(handler)
        handler.close()


@pytest.fixture(autouse=True)
def terminal_style(monkeypatch):
    """Messages as printed in a terminal (not in the GUI), with icons and without colors, whatever runs the tests."""
    monkeypatch.setattr(console, 'GUI_MODE', False)
    monkeypatch.setattr(console, 'STYLE', console.Style(icons=True, colors=False))
    monkeypatch.setattr(console, 'VERBOSE', False)
