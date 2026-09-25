import io
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
        status = 200

        def __init__(self, content: bytes):
            self.content = content

        def read(self):
            return self.content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    FEED = (b'<feed xmlns="http://www.w3.org/2005/Atom"><id>http://arxiv.org/api/x</id>'
            b'<entry><title>T</title></entry></feed>')

    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr(arXiv_api, 'T_SLEEP', 0)

    @pytest.fixture
    def curl_calls(self, monkeypatch):
        """Replace curl by a queue of responses (None means curl is not installed)."""
        responses = []
        calls = []

        def fake_curl(url):
            calls.append(url)
            return responses.pop(0) if responses else None

        monkeypatch.setattr(arXiv_api, '_fetch_curl', fake_curl)
        return responses, calls

    @staticmethod
    def _http_error(code: int, body: bytes = b'') -> urllib.error.HTTPError:
        return urllib.error.HTTPError('url', code, 'error', {}, io.BytesIO(body))

    def test_retries_until_success(self, monkeypatch, curl_calls):
        opener = self.FakeOpener([self._http_error(503), self.FakeResponse(self.FEED)])
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', opener)

        result = _get_arxiv_feed('https://example.org')

        assert opener.calls == 2
        assert result.entries[0].title == 'T'
        assert curl_calls[1] == []  # curl is only used for 406

    def test_raises_after_exhausting_retries(self, monkeypatch, curl_calls):
        opener = self.FakeOpener([self._http_error(503)] * (arXiv_api.N_RETRIES + 1))
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', opener)

        with pytest.raises(RuntimeError, match='503'):
            _get_arxiv_feed('https://example.org')
        assert opener.calls == arXiv_api.N_RETRIES + 1

    def test_network_errors_are_retried(self, monkeypatch, curl_calls):
        opener = self.FakeOpener([urllib.error.URLError('timed out'), self.FakeResponse(self.FEED)])
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', opener)

        assert _get_arxiv_feed('https://example.org').entries[0].title == 'T'

    def test_406_with_a_valid_feed_is_accepted(self, monkeypatch, curl_calls):
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', self.FakeOpener([self._http_error(406, self.FEED)]))

        assert _get_arxiv_feed('https://example.org').entries[0].title == 'T'
        assert curl_calls[1] == []

    def test_406_falls_back_to_curl(self, monkeypatch, curl_calls):
        responses, calls = curl_calls
        responses.append((200, self.FEED))
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', self.FakeOpener([self._http_error(406)]))

        assert _get_arxiv_feed('https://example.org').entries[0].title == 'T'
        assert calls == ['https://example.org']

    def test_406_without_curl_retries(self, monkeypatch, curl_calls):
        opener = self.FakeOpener([self._http_error(406), self.FakeResponse(self.FEED)])
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', opener)

        assert _get_arxiv_feed('https://example.org').entries[0].title == 'T'
        assert opener.calls == 2

    def test_empty_200_is_not_a_feed(self, monkeypatch, curl_calls):
        opener = self.FakeOpener([self.FakeResponse(b'')] * (arXiv_api.N_RETRIES + 1))
        monkeypatch.setattr(arXiv_api, 'ARXIV_OPENER', opener)

        with pytest.raises(RuntimeError, match='200'):
            _get_arxiv_feed('https://example.org')


class TestFetchCurl:
    def test_sends_the_arxiv_headers_and_splits_the_status(self, monkeypatch):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout=b'<feed/>\n200')

        monkeypatch.setattr(arXiv_api, 'run', fake_run)

        assert arXiv_api._fetch_curl('https://example.org') == (200, b'<feed/>')
        (args,) = calls
        assert args[0] == 'curl' and args[-1] == 'https://example.org'
        assert f"User-Agent: {arXiv_api.ARXIV_HEADERS['User-Agent']}" in args

    def test_missing_curl(self, monkeypatch):
        def not_installed(*args, **kwargs):
            raise FileNotFoundError

        monkeypatch.setattr(arXiv_api, 'run', not_installed)

        assert arXiv_api._fetch_curl('https://example.org') is None

    def test_curl_error(self, monkeypatch):
        monkeypatch.setattr(arXiv_api, 'run', lambda *a, **k: SimpleNamespace(returncode=6, stdout=b'\n000'))

        assert arXiv_api._fetch_curl('https://example.org') is None


@pytest.mark.network
def test_real_arxiv_request():
    grouped, dates = search_entries(['quant-ph'], datetime(2026, 9, 21), datetime(2026, 9, 22))

    assert len(dates) == 1
    assert grouped[0], 'arXiv returned no entries for a regular weekday'
