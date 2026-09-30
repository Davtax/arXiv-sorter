import hashlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from arxorter import java_runtime

JAVA_NAME = 'java.exe' if sys.platform == 'win32' else 'java'
TOP_FOLDER = 'jdk-21.0.8+9-jre'


def archive_bytes(name: str) -> bytes:
    """A small Java runtime archive, with the layout of the Temurin ones: a single folder with bin/java."""
    buffer = io.BytesIO()
    member = f'{TOP_FOLDER}/bin/{JAVA_NAME}'
    if name.endswith('.zip'):
        with zipfile.ZipFile(buffer, 'w') as zip_file:
            zip_file.writestr(member, b'java')
    else:
        with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
            info = tarfile.TarInfo(member)
            info.size = 4
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(b'java'))
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]


@pytest.fixture
def runtime_dir(tmp_path, monkeypatch):
    path = tmp_path / 'config' / 'java'
    monkeypatch.setattr(java_runtime, 'RUNTIME_DIR', path)
    return path


@pytest.fixture
def no_system_java(monkeypatch):
    monkeypatch.setattr(java_runtime, 'system_java', lambda: False)


def serve(monkeypatch, name: str, content: bytes, checksum: str | None = None):
    package = {'name': name, 'link': 'https://example.org/jre', 'size': len(content),
               'checksum': checksum or hashlib.sha256(content).hexdigest()}
    monkeypatch.setattr(java_runtime, 'runtime_package', lambda: package)
    monkeypatch.setattr(java_runtime.requests, 'get', lambda *args, **kwargs: FakeResponse(content))


def test_downloaded_runtime_is_preferred(runtime_dir, monkeypatch):
    java = runtime_dir / TOP_FOLDER / 'bin' / JAVA_NAME
    java.parent.mkdir(parents=True)
    java.write_bytes(b'java')
    monkeypatch.setattr(java_runtime, 'system_java', lambda: pytest.fail('system java checked'))

    assert java_runtime.find_java() == java


def test_system_java_is_used_without_download(runtime_dir, monkeypatch):
    monkeypatch.setattr(java_runtime, 'system_java', lambda: True)
    monkeypatch.setattr(java_runtime, 'download_java', lambda: pytest.fail('downloaded'))

    assert java_runtime.find_java() == 'java'


@pytest.mark.parametrize('name', ['OpenJDK21U-jre_x64_windows_hotspot.zip', 'OpenJDK21U-jre_x64_linux_hotspot.tar.gz'])
def test_runtime_is_downloaded_and_kept(runtime_dir, no_system_java, monkeypatch, capsys, name):
    serve(monkeypatch, name, archive_bytes(name))

    java = java_runtime.find_java()

    assert java == runtime_dir / TOP_FOLDER / 'bin' / JAVA_NAME and java.read_bytes() == b'java'
    assert sorted(path.name for path in runtime_dir.parent.iterdir()) == ['java']  # No temporary files left
    output = capsys.readouterr().out
    assert 'only needed the first time' in output and 'Java saved in' in output

    monkeypatch.setattr(java_runtime.requests, 'get', lambda *args, **kwargs: pytest.fail('downloaded again'))
    assert java_runtime.find_java() == java


def test_corrupted_download_is_discarded(runtime_dir, no_system_java, monkeypatch, capsys):
    name = 'jre.zip'
    serve(monkeypatch, name, archive_bytes(name), checksum='0' * 64)

    assert java_runtime.find_java() is None
    assert list(runtime_dir.parent.iterdir()) == []
    assert 'checksum does not match' in capsys.readouterr().out


def test_failed_download_disables_figures(runtime_dir, no_system_java, monkeypatch, capsys):
    def offline(*args, **kwargs):
        raise java_runtime.requests.ConnectionError('offline')

    monkeypatch.setattr(java_runtime.requests, 'get', offline)

    assert java_runtime.find_java() is None
    assert not runtime_dir.exists()
    assert 'Running without figure detection' in capsys.readouterr().out


def test_no_runtime_for_this_system(runtime_dir, no_system_java, monkeypatch, capsys):
    monkeypatch.setattr(java_runtime, 'runtime_package', lambda: None)

    assert java_runtime.find_java() is None
    assert 'no Java runtime to download for this system' in capsys.readouterr().out


def test_package_of_this_system_is_requested(monkeypatch):
    requests = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [{'binary': {'package': {'name': 'jre.zip'}}}]

    def get(url, params, timeout):
        requests.append(params)
        return Response()

    monkeypatch.setattr(java_runtime.sys, 'platform', 'darwin')
    monkeypatch.setattr(java_runtime.platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(java_runtime.requests, 'get', get)

    assert java_runtime.runtime_package() == {'name': 'jre.zip'}
    assert requests == [{'os': 'mac', 'architecture': 'aarch64', 'image_type': 'jre', 'vendor': 'eclipse'}]


def test_macos_layout_is_found(runtime_dir, monkeypatch):
    monkeypatch.setattr(java_runtime.sys, 'platform', 'darwin')
    java = runtime_dir / TOP_FOLDER / 'Contents' / 'Home' / 'bin' / 'java'
    java.parent.mkdir(parents=True)
    java.write_bytes(b'java')

    assert java_runtime.downloaded_java() == Path(java)
