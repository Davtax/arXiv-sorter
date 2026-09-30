import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from arxiv_sorter import system


@pytest.fixture
def frozen(monkeypatch):
    """Pretend to run as a PyInstaller binary located at the given path."""
    def set_executable(path: Path):
        monkeypatch.setattr(sys, 'frozen', True, raising=False)
        monkeypatch.setattr(sys, 'executable', str(path))
    return set_executable


def test_current_directory_when_run_from_python(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.chdir(tmp_path)

    assert system.base_dir() == tmp_path


def test_next_to_the_binary(frozen, tmp_path):
    frozen(tmp_path / 'arXiv-sorter-Windows.exe')

    assert system.base_dir() == tmp_path


def test_next_to_the_macos_app_bundle(frozen, tmp_path):
    frozen(tmp_path / 'arXiv-sorter.app' / 'Contents' / 'MacOS' / 'arXiv-sorter')

    assert system.base_dir() == tmp_path


def test_home_folder_for_translocated_macos_app(frozen, tmp_path, monkeypatch):
    monkeypatch.setattr(system.Path, 'home', lambda: tmp_path / 'home')
    (tmp_path / 'home').mkdir()
    frozen(tmp_path / 'AppTranslocation' / 'd' / 'arXiv-sorter.app' / 'Contents' / 'MacOS' / 'arXiv-sorter')

    assert system.base_dir() == tmp_path / 'home' / 'arXiv-sorter'
    assert system.base_dir().is_dir()


class TestProcessTree:
    def test_descendants_are_collected_recursively(self, monkeypatch):
        tree = {1: [2, 3], 2: [4], 3: [], 4: []}
        monkeypatch.setattr(system.subprocess, 'run', lambda args, **kwargs: SimpleNamespace(
            stdout='\n'.join(str(child) for child in tree[int(args[-1])])))

        assert system.descendant_pids(1) == [2, 3, 4]

    def test_no_descendants_without_pgrep(self, monkeypatch):
        def missing(*args, **kwargs):
            raise FileNotFoundError('pgrep')

        monkeypatch.setattr(system.subprocess, 'run', missing)

        assert system.descendant_pids(1) == []

    def test_posix_kills_the_whole_tree(self, monkeypatch):
        killed = []
        monkeypatch.setattr(system.sys, 'platform', 'linux')
        monkeypatch.setattr(system, 'descendant_pids', lambda pid: [11, 12])
        monkeypatch.setattr(system.os, 'kill', lambda pid, sig: killed.append(pid), raising=False)
        monkeypatch.setattr(system.signal, 'SIGKILL', 9, raising=False)

        system.kill_process_tree(10)

        assert killed == [10, 11, 12]


class TestConfigDir:
    @pytest.mark.parametrize(('platform', 'environment', 'expected'), [
        ('win32', {'LOCALAPPDATA': 'local'}, Path('local') / 'arXiv-sorter'),
        ('darwin', {}, Path('home') / 'Library' / 'Preferences' / 'arXiv-sorter'),
        ('linux', {}, Path('home') / '.config' / 'arXiv-sorter'),
        ('linux', {'XDG_CONFIG_HOME': 'xdg'}, Path('xdg') / 'arXiv-sorter'),
    ])
    def test_platform_folder(self, monkeypatch, platform, environment, expected):
        monkeypatch.setattr(system.sys, 'platform', platform)
        monkeypatch.setattr(system.Path, 'home', lambda: Path('home'))
        for name in ('LOCALAPPDATA', 'XDG_CONFIG_HOME'):
            monkeypatch.delenv(name, raising=False)
        for name, value in environment.items():
            monkeypatch.setenv(name, value)

        assert system.config_dir() == expected

    def test_same_folder_as_qt(self):
        """The GUI settings were saved by Qt in previous versions, they must still be found."""
        qt_core = pytest.importorskip('PySide6.QtCore')
        qt_core.QCoreApplication.setApplicationName(system.APP_NAME)
        location = qt_core.QStandardPaths.StandardLocation.AppConfigLocation

        assert Path(qt_core.QStandardPaths.writableLocation(location)) == system.config_dir()


class TestOriginalPath:
    def test_not_translocated_unchanged(self, tmp_path):
        assert system.original_path(tmp_path / 'arXiv-sorter.app') == tmp_path / 'arXiv-sorter.app'

    def test_unknown_translocation_unchanged(self, tmp_path):
        # Not a real translocation: the Security framework does not know it (and other systems do not have it)
        path = tmp_path / 'AppTranslocation' / 'ID' / 'd' / 'arXiv-sorter.app'
        path.mkdir(parents=True)
        assert system.original_path(path) == path
