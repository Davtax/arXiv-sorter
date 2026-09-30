import threading
import time
from types import SimpleNamespace

import requests

from arxorter import network
from arxorter.network import get_image


class TestGetUrlsAsync:
    def test_responses_in_the_order_of_the_urls(self, monkeypatch):
        def slow_first(url, **kwargs):
            time.sleep(0.05 if url.endswith('1') else 0)  # The first url answers last
            return SimpleNamespace(url=url)

        monkeypatch.setattr(network.requests, 'get', slow_first)
        urls = [f'https://arxiv.org/pdf/{i}' for i in range(1, 7)]

        assert [response.url for response in network.get_urls_async(urls, progress_bar=False)] == urls

    def test_failed_requests_are_none(self, monkeypatch):
        def flaky(url, **kwargs):
            if url.endswith('bad'):
                raise requests.ConnectionError('offline')
            return SimpleNamespace(url=url)

        monkeypatch.setattr(network.requests, 'get', flaky)

        responses = network.get_urls_async(['https://a/ok', 'https://a/bad'], progress_bar=False)

        assert responses[0].url == 'https://a/ok' and responses[1] is None

    def test_requests_run_concurrently_with_a_limit(self, monkeypatch):
        running, peak, lock = 0, 0, threading.Lock()

        def tracked(url, **kwargs):
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.02)
            with lock:
                running -= 1
            return SimpleNamespace(url=url)

        monkeypatch.setattr(network.requests, 'get', tracked)

        network.get_urls_async([f'https://a/{i}' for i in range(20)], progress_bar=False)

        assert 1 < peak <= network.MAX_WORKERS

    def test_timeout_and_headers(self, monkeypatch):
        calls = []
        monkeypatch.setattr(network.requests, 'get', lambda url, **kwargs: calls.append(kwargs))

        network.get_urls_async(['https://a/1'], progress_bar=False)

        assert calls == [{'headers': network.HEADERS, 'timeout': network.TIMEOUT}]

    def test_no_urls(self):
        assert network.get_urls_async([]) == []


class TestGetImage:
    def test_no_response(self):
        assert get_image(None) == ''

    def test_page_without_png(self):
        assert get_image(SimpleNamespace(text='<html><img src="x.jpg"></html>')) == ''

    def test_first_png_source(self):
        html = '<p><img class="ltx" src="x1.png" alt="Fig 1"></p><img src="x2.png">'
        assert get_image(SimpleNamespace(text=html)) == 'x1.png'
