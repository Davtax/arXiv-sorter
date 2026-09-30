"""
Full update from GitHub: an installed program that pretends to be the version just before the latest release finds
the release, downloads it, replaces itself with it, and the downloaded program runs and reports the new version.

The updates go through the same code as the programs: the update step of the command line program, and the update
checker and installer of the GUI. They download the real release assets (tens of MB), so they only run with
`pytest -m network`.
"""
import os
import plistlib
import subprocess
import sys
import time
import unicodedata
from argparse import Namespace
from pathlib import Path

import pytest
from packaging import version

from arxorter import console, pipeline, updater
from arxorter.gui import updates
from arxorter.system import kill_process_tree

pytestmark = pytest.mark.network

T_ALIVE = 10  # seconds the launched GUI must keep running
TIMEOUT = 120  # seconds for the new program to answer (the first start of a PyInstaller binary is slow)
# First release named arXorter: the previous ones have no arXorter assets to update to, so the updates are skipped
# until it is published
FIRST_ARXORTER_VERSION = '0.4.0'


def version_before(tag: str) -> str:
    """
    A version just lower than the one of the tag, e.g. 0.3.2 for v0.3.3 (0.2.999 for v0.3.0).
    """
    major, minor, micro = (*version.parse(tag).release, 0, 0)[:3]
    if micro:
        return f'{major}.{minor}.{micro - 1}'
    if minor:
        return f'{major}.{minor - 1}.999'
    return f'{major - 1}.999.999'


def fake_installed_program(folder: Path, gui: bool, old_version: str) -> Path:
    """
    Stand-in for the installed program of the old version, named as the release asset of this platform.
    """
    name = updater.asset_name(updater.get_system_name(), gui)
    if sys.platform == 'darwin' and gui:
        program = folder / f'{name}.app'
        (program / 'Contents' / 'MacOS').mkdir(parents=True)
        (program / 'Contents' / 'MacOS' / 'arXorter').write_text(f'old {old_version}')
        return program

    program = folder / (f'{name}.exe' if sys.platform == 'win32' else name)
    folder.mkdir(parents=True, exist_ok=True)
    program.write_text(f'old {old_version}')
    return program


def executable(program: Path) -> Path:
    """
    The binary to run: the program itself, or the executable inside a macOS app.
    """
    if program.suffix != '.app':
        return program
    with (program / 'Contents' / 'Info.plist').open('rb') as file:
        return program / 'Contents' / 'MacOS' / plistlib.load(file)['CFBundleExecutable']


def reported_version(program: Path, gui: bool) -> str:
    """
    Output of the program asked for its version (the GUI answers through its command line worker).
    """
    arguments = ['--worker', '--version'] if gui else ['--version']
    environment = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
    result = subprocess.run([str(executable(program)), *arguments], capture_output=True, text=True, timeout=TIMEOUT,
                            env=environment, cwd=program.parent)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def quarantine(path: Path):
    """
    Mark the path as downloaded from the internet, as macOS does with the files of web browsers.
    """
    subprocess.run(['xattr', '-w', 'com.apple.quarantine', '0081;00000000;Safari;', str(path)], check=True)


def is_quarantined(path: Path) -> bool:
    attributes = subprocess.run(['xattr', '-r', str(path)], capture_output=True, text=True).stdout
    return 'com.apple.quarantine' in attributes


def update_with_the_gui(qapp) -> tuple[updater.Release, Path]:
    """
    What the window does: check for updates, and install the release found. Both run here in the thread of the test.
    """
    checked = []
    checker = updates.UpdateChecker()
    checker.checked.connect(lambda release, message: checked.append((release, message)))
    checker.run()
    release, message = checked[0]
    assert release is not None, message or 'No update found'

    installed, failed, received = [], [], []
    installer = updates.UpdateInstaller(release)
    installer.progress.connect(lambda done, total: received.append(done))
    installer.installed.connect(installed.append)
    installer.failed.connect(failed.append)
    installer.run()
    assert not failed, failed[0]
    assert received[-1] == release.size  # The download went to the end, checked against the size and checksum
    return release, installed[0]


@pytest.fixture(scope='module')
def latest() -> dict:
    return updater.latest_release()


@pytest.fixture
def old_version(latest, monkeypatch) -> str:
    """
    Pretend the running program is the version just before the latest release, so the update is found.
    """
    if version.parse(latest['tag_name']) < version.parse(FIRST_ARXORTER_VERSION):
        pytest.skip(f'The latest release ({latest["tag_name"]}) is from before the rename, and its assets are named '
                    f'arXiv-sorter')
    old = version_before(latest['tag_name'])
    monkeypatch.setattr(pipeline, '__version__', old)
    monkeypatch.setattr(updates, '__version__', old)
    return old


@pytest.fixture
def downloads(tmp_path) -> Path:
    """
    Folder where the user has the program, with spaces and non-ASCII characters (as in a synced cloud folder).
    """
    return tmp_path / 'Cloud Drive-Müllerstraße' / 'My Downloads'


@pytest.fixture
def installed_at(monkeypatch):
    """
    Make the fake program the installed one, which the updates replace.
    """
    def set_installed(path: Path) -> Path:
        monkeypatch.setattr(updater, 'installed_path', lambda: path)
        return path
    return set_installed


@pytest.fixture
def isolated_home(tmp_path, monkeypatch) -> dict[str, str]:
    """
    Home folder of the programs started by the tests, so they do not use the settings of the user, and no display.
    """
    home = tmp_path / 'home'
    home.mkdir()
    environment = {'HOME': str(home), 'LOCALAPPDATA': str(home / 'AppData' / 'Local'),
                   'XDG_CONFIG_HOME': str(home / '.config'), 'QT_QPA_PLATFORM': 'offscreen'}
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return environment


@pytest.mark.parametrize('tag, expected', [('v0.3.3', '0.3.2'), ('v0.3.0', '0.2.999'), ('v1.0', '0.999.999')])
def test_version_before(tag, expected):
    assert version.parse(version_before(tag)) < version.parse(tag)
    assert version_before(tag) == expected


def test_up_to_date_program_does_not_download(latest, qapp, monkeypatch):
    monkeypatch.setattr(updates, '__version__', latest['tag_name'].removeprefix('v'))
    checked = []
    checker = updates.UpdateChecker()
    checker.checked.connect(lambda release, message: checked.append((release, message)))
    checker.run()
    assert checked == [(None, '')]


def test_command_line_program_updated(latest, old_version, downloads, installed_at, monkeypatch, capsys):
    installed = installed_at(fake_installed_program(downloads, gui=False, old_version=old_version))
    monkeypatch.setattr(pipeline, 'gui_mode', lambda: False)
    monkeypatch.setattr(pipeline, 'is_frozen', lambda: True)
    monkeypatch.setattr(console, 'question', lambda text: True)  # The user accepts the update

    with pytest.raises(SystemExit):  # Once updated, the program exits to be run again
        pipeline._check_updates(Namespace(update=True))

    assert f'updated to {latest["tag_name"]}' in capsys.readouterr().out
    assert not (installed.parent / updater.UPDATE_DIR).exists()
    old = updater.old_version_path(installed)
    assert old.read_text() == f'old {old_version}'  # Kept until the next start, since it may still be running
    assert latest['tag_name'].removeprefix('v') in reported_version(installed, gui=False)

    updater.remove_old_version()  # What the new program does when it starts
    assert not old.exists()


def test_gui_updated(latest, old_version, downloads, installed_at, qapp):
    installed = installed_at(fake_installed_program(downloads, gui=True, old_version=old_version))

    release, program = update_with_the_gui(qapp)

    assert release.version == latest['tag_name']
    assert program == installed
    assert not (installed.parent / updater.UPDATE_DIR).exists()
    assert updater.old_version_path(installed).exists()
    assert release.version.removeprefix('v') in reported_version(program, gui=True)


@pytest.mark.skipif(sys.platform != 'darwin', reason='App Translocation of macOS')
def test_translocated_app_updated(old_version, downloads, installed_at, tmp_path, qapp, monkeypatch):
    """
    The app runs from a random read-only copy made by macOS: the update replaces it where the user has it, and removes
    the quarantine of the new app, so macOS runs it from there.
    """
    installed = fake_installed_program(downloads, gui=True, old_version=old_version)
    quarantine(installed)
    translocated = installed_at(tmp_path / 'AppTranslocation' / 'ID' / 'd' / installed.name)
    # Real translocations can only be made by macOS, when it starts the app
    monkeypatch.setattr(updater, 'original_path', lambda path: installed if path == translocated else path)

    extract = updater.extract

    def extract_quarantined(archive: Path, folder: Path) -> Path:
        # The update does not quarantine its download, but macOS may (e.g. through a security policy)
        program = extract(archive, folder)
        quarantine(program)
        return program

    monkeypatch.setattr(updater, 'extract', extract_quarantined)

    release, program = update_with_the_gui(qapp)

    assert program == installed
    assert is_quarantined(updater.old_version_path(installed))  # The previous app, moved aside as it was
    assert not is_quarantined(program)
    assert release.version.removeprefix('v') in reported_version(program, gui=True)


def test_updated_gui_is_launched(old_version, downloads, installed_at, isolated_home, qapp, monkeypatch):
    """
    After the update, the GUI starts the new version (as it does before closing), which keeps running.
    """
    installed_at(fake_installed_program(downloads, gui=True, old_version=old_version))
    _, program = update_with_the_gui(qapp)

    started = []
    popen = subprocess.Popen

    def recording_popen(command, **options):
        if command[0] == 'open':  # Apps opened by macOS do not get the environment, only the variables given to open
            command = ['open', *[f'--env={name}={value}' for name, value in isolated_home.items()], *command[1:]]
        process = popen(command, **options)
        started.append(process)
        return process

    monkeypatch.setattr(updater.subprocess, 'Popen', recording_popen)
    updater.launch(program)
    assert len(started) == 1

    if program.suffix == '.app':  # `open` exits once the app is started
        assert started[0].wait(timeout=TIMEOUT) == 0
    time.sleep(T_ALIVE)
    pids = running_pids(program)
    for pid in pids:
        kill_process_tree(pid)

    assert pids, f'{program.name} did not keep running after the update'


def running_pids(program: Path) -> list[int]:
    """
    Processes running the executable of the program.
    """
    if sys.platform == 'win32':
        name = executable(program).name
        result = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], capture_output=True,
                                text=True)
        return [int(line.split('","')[1]) for line in result.stdout.splitlines() if line.startswith(f'"{name}"')]

    # Compared in the same Unicode form: macOS may write the non-ASCII characters of the path decomposed
    target = unicodedata.normalize('NFC', str(executable(program)))
    result = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True)
    lines = (line.strip().split(maxsplit=1) for line in result.stdout.splitlines())
    return [int(line[0]) for line in lines
            if len(line) == 2 and unicodedata.normalize('NFC', line[1]).startswith(target)]
