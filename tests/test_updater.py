import hashlib
import io
import os
import sys
import tarfile
import time
import zipfile

import pytest
import requests

from arxiv_sorter import updater
from arxiv_sorter.updater import Release, UpdateCancelled, UpdateError


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, content=b''):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.content = content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} error')

    def iter_content(self, chunk_size):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start:start + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


RELEASE = {
    'tag_name': 'v1.0.0',
    'html_url': 'https://github.com/Davtax/arXiv-sorter/releases/tag/v1.0.0',
    'body': 'New features',
    'assets': [
        {'name': 'arXiv-sorter-GUI-Windows.zip', 'browser_download_url': 'https://example.org/gui-windows.zip',
         'size': 3, 'digest': 'sha256:abc'},
        {'name': 'arXiv-sorter-Windows.zip', 'browser_download_url': 'https://example.org/windows.zip'},
        {'name': 'arXiv-sorter-Ubuntu.zip', 'browser_download_url': 'https://example.org/ubuntu.zip'},
        {'name': 'arXiv-sorter-GUI-Ubuntu.tar.gz', 'browser_download_url': 'https://example.org/gui-ubuntu.tar.gz'},
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


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_file:
        for name, data in files.items():
            zip_file.writestr(name, data)
    return buffer.getvalue()


def tar_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def release_for(content: bytes, asset: str = 'arXiv-sorter-GUI-Windows.zip', **kwargs) -> Release:
    return Release(version='v1.0.0', url=f'https://example.org/{asset}', asset=asset, **kwargs)


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
        release = updater.check_for_update('Windows', '0.9.0')
        assert release.url == 'https://example.org/windows.zip'
        assert release.version == 'v1.0.0'
        assert release.page == RELEASE['html_url']
        assert release.notes == 'New features'

    @pytest.mark.parametrize(('platform', 'expected'), [('Windows', 'https://example.org/gui-windows.zip'),
                                                        ('Ubuntu', 'https://example.org/gui-ubuntu.tar.gz')])
    def test_gui_returns_gui_asset(self, github, platform, expected):
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update(platform, '0.9.0', gui=True).url == expected

    def test_size_and_digest_of_the_asset(self, github):
        github.append(FakeResponse(json_data=RELEASE))
        release = updater.check_for_update('Windows', '0.9.0', gui=True)
        assert (release.asset, release.size, release.digest) == ('arXiv-sorter-GUI-Windows.zip', 3, 'sha256:abc')

    @pytest.mark.parametrize('current', ['1.0.0', '1.0.1'])
    def test_up_to_date(self, github, current):
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update('Windows', current) is None

    def test_missing_platform_asset(self, github, capsys, verbose):
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update('macOS', '0.9.0') is None
        assert 'No asset arXiv-sorter-macOS found' in capsys.readouterr().out

    def test_no_internet(self, github, capsys):
        github.append(requests.ConnectionError())
        assert updater.check_for_update('Windows', '0.9.0') is None
        assert 'No internet connection' in capsys.readouterr().out

    def test_long_rate_limit_gives_up(self, github, monkeypatch):
        monkeypatch.setattr(updater, 'sleep', lambda _: None)
        github.append(FakeResponse(403, headers={'X-RateLimit-Reset': str(int(time.time()) + 3600)}))
        assert updater.check_for_update('Windows', '0.9.0') is None

    def test_short_rate_limit_retries(self, github, monkeypatch):
        monkeypatch.setattr(updater, 'sleep', lambda _: None)
        monkeypatch.setattr(updater, 'timing_message', lambda *args: None)
        github.append(FakeResponse(429, headers={'X-RateLimit-Reset': str(int(time.time()) + 2)}))
        github.append(FakeResponse(json_data=RELEASE))
        assert updater.check_for_update('Windows', '0.9.0').url == 'https://example.org/windows.zip'

    def test_unexpected_status_does_not_loop_forever(self, github):
        github.append(FakeResponse(500))
        assert updater.check_for_update('Windows', '0.9.0') is None


class TestLatestRelease:
    def test_offline_error(self, github):
        github.append(requests.ConnectionError())
        with pytest.raises(updater.OfflineError):
            updater.latest_release()

    def test_status_error(self, github):
        github.append(FakeResponse(500))
        with pytest.raises(UpdateError, match='status code 500'):
            updater.latest_release()


class TestDownload:
    def test_saved_with_progress(self, github, tmp_path):
        content = b'x' * 150_000
        github.append(FakeResponse(content=content, headers={'Content-Length': str(len(content))}))
        progress = []

        path = updater.download(release_for(content, size=len(content)), tmp_path,
                                lambda received, total: progress.append((received, total)))

        assert path == tmp_path / 'arXiv-sorter-GUI-Windows.zip'
        assert path.read_bytes() == content
        assert progress[-1] == (len(content), len(content))
        assert len(progress) > 1

    def test_checksum_verified(self, github, tmp_path):
        content = b'program'
        github.append(FakeResponse(content=content))
        digest = 'sha256:' + hashlib.sha256(content).hexdigest()
        assert updater.download(release_for(content, digest=digest), tmp_path).read_bytes() == content

    def test_corrupted(self, github, tmp_path):
        github.append(FakeResponse(content=b'program'))
        with pytest.raises(UpdateError, match='corrupted'):
            updater.download(release_for(b'', digest='sha256:' + '0' * 64), tmp_path)

    def test_incomplete(self, github, tmp_path):
        github.append(FakeResponse(content=b'prog'))
        with pytest.raises(UpdateError, match='incomplete'):
            updater.download(release_for(b'', size=7), tmp_path)

    def test_http_error(self, github, tmp_path):
        github.append(FakeResponse(404))
        with pytest.raises(UpdateError, match='Unable to download'):
            updater.download(release_for(b''), tmp_path)

    def test_cancelled(self, github, tmp_path):
        github.append(FakeResponse(content=b'program'))

        def cancel(received, total):
            raise UpdateCancelled

        with pytest.raises(UpdateCancelled):
            updater.download(release_for(b''), tmp_path, cancel)

    def test_asset_name_cannot_leave_the_folder(self, github, tmp_path):
        github.append(FakeResponse(content=b'program'))
        folder = tmp_path / 'folder'
        folder.mkdir()
        path = updater.download(release_for(b'', asset='../evil.zip'), folder)
        assert path == folder / 'evil.zip'


class TestExtract:
    def test_zip(self, tmp_path):
        archive = tmp_path / 'arXiv-sorter-GUI-Windows.zip'
        archive.write_bytes(zip_bytes({'arXiv-sorter-GUI.exe': b'new'}))
        program = updater.extract(archive, tmp_path / 'out')
        assert program.name == 'arXiv-sorter-GUI.exe'
        assert program.read_bytes() == b'new'

    def test_tar(self, tmp_path):
        archive = tmp_path / 'arXiv-sorter-GUI-Ubuntu.tar.gz'
        archive.write_bytes(tar_bytes({'arXiv-sorter-GUI': b'new'}))
        program = updater.extract(archive, tmp_path / 'out')
        assert program.read_bytes() == b'new'
        if os.name != 'nt':
            assert os.access(program, os.X_OK)

    def test_more_than_one_program(self, tmp_path):
        archive = tmp_path / 'release.zip'
        archive.write_bytes(zip_bytes({'a': b'1', 'b': b'2'}))
        with pytest.raises(UpdateError, match='Unexpected content'):
            updater.extract(archive, tmp_path / 'out')

    def test_not_an_archive(self, tmp_path):
        archive = tmp_path / 'release.zip'
        archive.write_bytes(b'not a zip')
        with pytest.raises(UpdateError, match='Unable to extract'):
            updater.extract(archive, tmp_path / 'out')

    def test_unknown_format(self, tmp_path):
        archive = tmp_path / 'release.rar'
        archive.write_bytes(b'')
        with pytest.raises(UpdateError, match='Unknown archive format'):
            updater.extract(archive, tmp_path / 'out')


class TestReplace:
    def test_old_version_kept_aside(self, tmp_path):
        installed = tmp_path / 'arXiv-sorter-GUI.exe'
        installed.write_bytes(b'old')
        new = tmp_path / 'new' / 'arXiv-sorter-GUI.exe'
        new.parent.mkdir()
        new.write_bytes(b'new')

        updater.replace(installed, new)

        assert installed.read_bytes() == b'new'
        assert updater.old_version_path(installed).read_bytes() == b'old'

        updater.remove_old_version(installed)
        assert not updater.old_version_path(installed).exists()

    def test_leftover_of_a_previous_update_replaced(self, tmp_path):
        installed = tmp_path / 'arXiv-sorter.app'
        (installed / 'Contents').mkdir(parents=True)
        (tmp_path / 'arXiv-sorter.app.old' / 'Contents').mkdir(parents=True)
        new = tmp_path / 'new' / 'arXiv-sorter.app'
        (new / 'Contents').mkdir(parents=True)
        (new / 'Contents' / 'version').write_text('new')

        updater.replace(installed, new)

        assert (installed / 'Contents' / 'version').read_text() == 'new'

    def test_restored_if_the_new_version_cannot_be_moved(self, tmp_path):
        installed = tmp_path / 'arXiv-sorter-GUI'
        installed.write_bytes(b'old')

        with pytest.raises(OSError):
            updater.replace(installed, tmp_path / 'missing')

        assert installed.read_bytes() == b'old'

    def test_remove_old_version_without_one(self, tmp_path):
        updater.remove_old_version(tmp_path / 'arXiv-sorter-GUI')  # Nothing to remove, no error


class TestInstallUpdate:
    def test_installed(self, github, tmp_path):
        installed = tmp_path / 'arXiv-sorter-GUI.exe'
        installed.write_bytes(b'old')
        content = zip_bytes({'arXiv-sorter-GUI.exe': b'new'})
        github.append(FakeResponse(content=content))

        program = updater.install_update(release_for(content, size=len(content)), installed=installed)

        assert program == installed
        assert installed.read_bytes() == b'new'
        assert not (tmp_path / updater.UPDATE_DIR).exists()

    def test_failed_download_keeps_the_installed_version(self, github, tmp_path):
        installed = tmp_path / 'arXiv-sorter-GUI.exe'
        installed.write_bytes(b'old')
        github.append(requests.ConnectionError('offline'))

        with pytest.raises(UpdateError):
            updater.install_update(release_for(b''), installed=installed)

        assert installed.read_bytes() == b'old'
        assert not updater.old_version_path(installed).exists()
        assert not (tmp_path / updater.UPDATE_DIR).exists()

    def test_read_only_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(updater.os, 'access', lambda path, mode: False)
        with pytest.raises(UpdateError, match='Unable to write'):
            updater.install_update(release_for(b''), installed=tmp_path / 'arXiv-sorter-GUI')


class TestLaunch:
    @pytest.fixture
    def popen(self, monkeypatch):
        calls = []
        monkeypatch.setattr(updater.subprocess, 'Popen', lambda command, **kwargs: calls.append((command, kwargs)))
        return calls

    def test_binary(self, popen, tmp_path, monkeypatch):
        monkeypatch.setenv('LD_LIBRARY_PATH', '/tmp/_MEI123')
        monkeypatch.setenv('LD_LIBRARY_PATH_ORIG', '/usr/lib')
        program = tmp_path / 'arXiv-sorter-GUI'

        updater.launch(program)

        command, kwargs = popen[0]
        assert command == [str(program)]
        assert kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'] == '1'
        assert kwargs['env']['LD_LIBRARY_PATH'] == '/usr/lib'
        assert 'LD_LIBRARY_PATH_ORIG' not in kwargs['env']
        assert kwargs['cwd'] == tmp_path

    def test_library_path_of_pyinstaller_removed(self, popen, tmp_path, monkeypatch):
        monkeypatch.setenv('LD_LIBRARY_PATH', '/tmp/_MEI123')
        monkeypatch.delenv('LD_LIBRARY_PATH_ORIG', raising=False)
        updater.launch(tmp_path / 'arXiv-sorter-GUI')
        assert 'LD_LIBRARY_PATH' not in popen[0][1]['env']

    def test_macos_app(self, popen, tmp_path):
        updater.launch(tmp_path / 'arXiv-sorter.app')
        assert popen[0][0] == ['open', '-n', str(tmp_path / 'arXiv-sorter.app')]


class TestDownloadAndUpdate:
    def test_exits_once_updated(self, monkeypatch, capsys):
        monkeypatch.setattr(updater, 'install_update', lambda release: updater.Path('arXiv-sorter-Windows.exe'))
        with pytest.raises(SystemExit):
            updater.download_and_update(release_for(b''))
        assert 'updated to v1.0.0' in capsys.readouterr().out

    def test_error_reported(self, monkeypatch, capsys):
        def fail(release):
            raise UpdateError('Unable to write in C:\\Program Files')

        monkeypatch.setattr(updater, 'install_update', fail)
        updater.download_and_update(release_for(b''))  # Does not exit, the old version keeps running
        assert 'Unable to write' in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != 'darwin', reason='ditto is only available on macOS')
def test_extract_macos_app(tmp_path):
    archive = tmp_path / 'arXiv-sorter-GUI-macOS.zip'
    archive.write_bytes(zip_bytes({'arXiv-sorter.app/Contents/MacOS/arXiv-sorter': b'new'}))
    program = updater.extract(archive, tmp_path / 'out')
    assert program.name == 'arXiv-sorter.app'
