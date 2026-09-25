import urllib.error
from datetime import datetime
from types import SimpleNamespace

import pytest

from app import arXiv_api
from app.arXiv_api import _get_arxiv_feed, _sort_entries, search_entries

# 2026-09-21 is a Monday
MON = datetime(2026, 9, 21, 18)


def _entry(updated: str) -> SimpleNamespace:
    return SimpleNamespace(updated=updated)


class TestSortEntries:
    def test_weekdays_are_separated_and_friday_groups_the_weekend(self):
        entries = [_entry('2026-09-28T10:00:00Z'),  # Monday before the deadline -> Friday mail
                   _entry('2026-09-21T19:00:00Z'),  # Monday
                   _entry('2026-09-22T12:00:00Z'),  # Monday mail (before Tuesday's deadline)
                   _entry('2026-09-26T12:00:00Z'),  # Saturday -> Friday mail
                   _entry('2026-09-25T20:00:00Z'),  # Friday
                   ]

        grouped, dates = _sort_entries(entries, MON, datetime(2026, 9, 28, 18))

        assert dates == [datetime(2026, 9, d, 18) for d in (21, 22, 23, 24, 25)]
        assert [len(day) for day in grouped] == [2, 0, 0, 0, 3]
        assert [e.updated for e in grouped[4]] == ['2026-09-25T20:00:00Z', '2026-09-26T12:00:00Z',
                                                   '2026-09-28T10:00:00Z']

    def test_entries_out_of_range_go_to_the_last_date(self, capsys):
        entries = [_entry('2026-09-21T19:00:00Z'), _entry('2026-09-30T12:00:00Z')]

        grouped, _ = _sort_entries(entries, MON, datetime(2026, 9, 23, 18))

        assert [len(day) for day in grouped] == [1, 1]
        assert 'not sorted' in capsys.readouterr().out


class TestSearchEntries:
    @pytest.fixture
    def requested_urls(self, monkeypatch):
        urls = []

        def fake_feed(url):
            urls.append(url)
            return SimpleNamespace(entries=[])

        monkeypatch.setattr(arXiv_api, '_get_arxiv_feed', fake_feed)
        return urls

    def test_query_contains_dates_and_categories(self, requested_urls):
        search_entries(['quant-ph', 'cond-mat'], datetime(2026, 9, 21), datetime(2026, 9, 24))

        (url,) = requested_urls
        assert url.startswith(arXiv_api.BASE_URL)
        assert 'search_query=lastUpdatedDate:[20260921' in url
        assert '+TO+20260924' in url
        assert '+AND+cat:(quant-ph*+OR+cond-mat*)' in url
        assert '&start=0&max_results=' in url

    def test_query_without_categories(self, requested_urls):
        search_entries([], datetime(2026, 9, 21), datetime(2026, 9, 24))

        assert 'cat:' not in requested_urls[0]

    def test_results_are_paginated(self, monkeypatch):
        pages = [[_entry('2026-09-21T19:00:00Z'), _entry('2026-09-21T20:00:00Z')], [_entry('2026-09-21T21:00:00Z')], ]
        urls = []

        def fake_feed(url):
            urls.append(url)
            return SimpleNamespace(entries=pages[len(urls) - 1])

        monkeypatch.setattr(arXiv_api, 'N_MAX', 2)
        monkeypatch.setattr(arXiv_api, '_get_arxiv_feed', fake_feed)

        grouped, _ = search_entries([], datetime(2026, 9, 21), datetime(2026, 9, 22))

        assert ['&start=0&' in urls[0], '&start=2&' in urls[1]] == [True, True]
        assert sum(len(day) for day in grouped) == 3


class TestGetArxivFeed:
    class FakeOpener:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = 0

        def open(self, request, timeout):
            self.calls += 1
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

    class FakeResponse:
        def __init__(self, content: bytes):
            self.content = content

        def read(self):
            return self.content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr(arXiv_api, 'T_SLEEP', 0)

    @staticmethod
    def _http_error(code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError('url', code, 'error', {}, None)

    def test_retries_until_success(self, monkeypatch):
        feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title></entry></feed>'
        opener = self.FakeOpener([self._http_error(503), self.FakeResponse(feed)])
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', opener)

        result = _get_arxiv_feed('https://example.org')

        assert opener.calls == 2
        assert result.entries[0].title == 'T'

    def test_raises_after_exhausting_retries(self, monkeypatch):
        opener = self.FakeOpener([self._http_error(503)] * (arXiv_api.N_RETRIES + 1))
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', opener)

        with pytest.raises(RuntimeError, match='503'):
            _get_arxiv_feed('https://example.org')
        assert opener.calls == arXiv_api.N_RETRIES + 1


@pytest.mark.network
def test_real_arxiv_request():
    grouped, dates = search_entries(['quant-ph'], datetime(2026, 9, 21), datetime(2026, 9, 22))

    assert len(dates) == 1
    assert grouped[0], 'arXiv returned no entries for a regular weekday'
