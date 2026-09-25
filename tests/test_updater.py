import time

import pytest
import requests

from updater import updater


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}

    def json(self):
        return self._json


RELEASE = {
    'tag_name': 'v1.0.0',
    'assets': [
        {'name': 'arXiv-sorter-Windows.zip', 'browser_download_url': 'https://example.org/windows.zip'},
        {'name': 'arXiv-sorter-Ubuntu.zip', 'browser_download_url': 'https://example.org/ubuntu.zip'},
    ],
}


@pytest.fixture
def github(monkeypatch):
    """Replace `requests.get` with a queue of fake responses."""
    responses = []

    def fake_get(url, **kwargs):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(updater.requests, 'get', fake_get)
    return responses


@pytest.mark.parametrize(('system', 'expected'), [('Darwin', 'macOS'), ('Windows', 'Windows'), ('Linux', 'Ubuntu')])
def test_get_system_name(monkeypatch, system, expected):
    monkeypatch.setattr(updater, 'system', lambda: system)
    assert updater.get_system_name() == expected


def test_get_system_name_unknown_platform(monkeypatch):
    monkeypatch.setattr(updater, 'system', lambda: 'Plan9')
    with pytest.raises(SystemExit):
        updater.get_system_name()


class TestCheckForUpdate:
    def test_newer_version_returns_platform_asset(self, github):
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update('Windows', '0.9.0') == 'https://example.org/windows.zip'

    @pytest.mark.parametrize('current', ['1.0.0', '1.0.1'])
    def test_up_to_date(self, github, current):
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update('Windows', current) is None

    def test_missing_platform_asset(self, github, capsys):
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update('macOS', '0.9.0') is None
        assert 'No asset found for macOS' in capsys.readouterr().out

    def test_no_internet(self, github):
        github.append(requests.ConnectionError())
        assert updater.check_for_update('Windows', '0.9.0') is None

    def test_long_rate_limit_gives_up(self, github, monkeypatch):
        monkeypatch.setattr(updater, 'sleep', lambda _: None)
        github.append(FakeResponse(403, headers={'X-RateLimit-Reset': str(int(time.time()) + 3600)}))
        assert updater.check_for_update('Windows', '0.9.0') is None

    def test_short_rate_limit_retries(self, github, monkeypatch):
        monkeypatch.setattr(updater, 'sleep', lambda _: None)
        monkeypatch.setattr(updater, 'timing_message', lambda *args: None)
        github.append(FakeResponse(429, headers={'X-RateLimit-Reset': str(int(time.time()) + 2)}))
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update('Windows', '0.9.0') == 'https://example.org/windows.zip'

    def test_unexpected_status_does_not_loop_forever(self, github):
        github.append(FakeResponse(500))
        assert updater.check_for_update('Windows', '0.9.0') is None
