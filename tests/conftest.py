from collections.abc import Callable

import pytest
from feedparser import FeedParserDict


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
