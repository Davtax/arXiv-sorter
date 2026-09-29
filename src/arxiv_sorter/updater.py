"""
Updates from the GitHub releases: check for a new version, and replace the installed binary (or macOS app) with it.

The running program cannot be overwritten on Windows, but it can be renamed, so the update moves the installed program
aside (to `<name>.old`), puts the new one in its place, and starts it. The old copy is removed the next time the
program starts (see `remove_old_version`).
"""
import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from platform import system
from time import sleep

import requests
from packaging import version

from arxiv_sorter import console
from arxiv_sorter.console import timing_message
from arxiv_sorter.dates import current_utc_timestamp
from arxiv_sorter.system import installed_path

URL = 'https://api.github.com/repos/Davtax/arXiv-sorter/releases/latest'
TIMEOUT = 10  # seconds
DOWNLOAD_TIMEOUT = 30  # seconds without receiving data before giving up the download
CHUNK_SIZE = 64 * 1024  # bytes
MAX_WAIT = 10  # maximum seconds to wait for the GitHub rate limit to reset

PLATFORMS = {'Darwin': 'macOS', 'Windows': 'Windows', 'Linux': 'Ubuntu'}

UPDATE_DIR = '.arXiv-sorter-update'  # Temporary folder next to the program, for the download
OLD_SUFFIX = '.old'  # Previous version, kept until the next start since it may still be running

Progress = Callable[[int, int], None]  # Bytes downloaded, and total bytes (0 if unknown)


class UpdateError(Exception):
    """
    The update could not be checked or installed. The message is meant for the user.
    """


class OfflineError(UpdateError):
    """
    GitHub could not be reached.
    """


class UpdateCancelled(Exception):
    """
    Raised by the progress callback to stop the download.
    """


@dataclass(frozen=True)
class Release:
    """
    A newer version of the program, and the asset to download for this platform.
    """
    version: str  # Tag of the release, e.g. v0.4.0
    url: str  # Download url of the asset
    asset: str  # Name of the asset, e.g. arXiv-sorter-GUI-Windows.zip
    size: int = 0  # Bytes, 0 if unknown
    digest: str = ''  # e.g. sha256:…, when GitHub provides it
    page: str = ''  # Web page of the release
    notes: str = ''  # Description of the release (Markdown)


def get_system_name() -> str:
    """
    Name of the current platform, as used in the names of the release assets.
    """
    try:
        return PLATFORMS[system()]
    except KeyError:
        sys.exit(f'Unknown platform {system()}')


def asset_name(platform: str, gui: bool = False) -> str:
    """
    Name (without extension) of the release asset for the platform, e.g. arXiv-sorter-CLI-Windows or
    arXiv-sorter-GUI-macOS. It is also the name of the program inside (plus .exe on Windows, or .app on macOS).
    """
    return f'arXiv-sorter-{"GUI" if gui else "CLI"}-{platform}'


def latest_release() -> dict:
    """
    Description of the latest release in GitHub (JSON of the GitHub API). Raises UpdateError if it is not available.
    """
    try:
        while True:
            response = requests.get(URL, timeout=TIMEOUT)
            if response.status_code == 200:
                return response.json()
            elif response.status_code in (403, 429):
                sleep(1)  # Wait 1 second and try again
                console.detail('Too many requests to GitHub, waiting to check for updates')
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = reset_time - int(current_utc_timestamp()) + 1
                if not 0 < wait_time <= MAX_WAIT:  # If the waiting time is too long (or unknown), give up
                    raise UpdateError('Too many requests to GitHub, try again later')
                timing_message(wait_time, 'until the next request to GitHub …')
            else:
                raise UpdateError(f'Unable to check for updates (GitHub status code {response.status_code})')

    except requests.RequestException as error:
        raise OfflineError('No internet connection, unable to check for updates') from error


def find_update(release: dict, platform: str, current_version: str, gui: bool = False) -> Release | None:
    """
    The release if it is newer than the current version and has an asset for the platform (of the GUI or of the
    command line program), None otherwise.
    """
    latest_version = release['tag_name']
    console.detail(f'Latest release on GitHub: {latest_version} (this is v{current_version})')

    if version.parse(f'v{current_version}') >= version.parse(latest_version):
        return None

    name = asset_name(platform, gui)
    for asset in release.get('assets', []):
        if asset['name'].split('.')[0] == name:  # The extension depends on the platform (.zip, .tar.gz)
            return Release(version=latest_version, url=asset['browser_download_url'], asset=asset['name'],
                           size=asset.get('size') or 0, digest=asset.get('digest') or '',
                           page=release.get('html_url') or '', notes=release.get('body') or '')

    console.detail(f'No asset {name} found in the latest release')
    return None


def check_for_update(platform: str, current_version: str, gui: bool = False) -> Release | None:
    """
    Check in GitHub if there is a new version available, and return it (None if there is none, or GitHub is not
    available).
    """
    try:
        release = latest_release()
    except OfflineError as error:
        console.warning(str(error), icon='🌐')
        return None
    except UpdateError as error:
        console.detail(str(error))
        return None

    return find_update(release, platform, current_version, gui)


# ------------------------------------------------------------------------------------------------------------ install
def download(release: Release, folder: Path, progress: Progress | None = None) -> Path:
    """
    Download the asset of the release into the folder, checking its size and checksum.
    """
    path = folder / Path(release.asset).name
    checksum = hashlib.sha256()
    received = 0
    try:
        with requests.get(release.url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
            response.raise_for_status()
            total = int(response.headers.get('Content-Length') or release.size or 0)
            with path.open('wb') as file:
                for chunk in response.iter_content(CHUNK_SIZE):
                    file.write(chunk)
                    checksum.update(chunk)
                    received += len(chunk)
                    if progress is not None:
                        progress(received, total)
    except requests.RequestException as error:
        raise UpdateError(f'Unable to download {release.asset}: {error}') from error

    if release.size and received != release.size:
        raise UpdateError(f'The download of {release.asset} is incomplete ({received} of {release.size} bytes)')
    algorithm, _, expected = release.digest.partition(':')
    if algorithm == 'sha256' and checksum.hexdigest() != expected.lower():
        raise UpdateError(f'The download of {release.asset} is corrupted (its checksum does not match)')
    return path


def extract(archive: Path, folder: Path) -> Path:
    """
    Extract the archive of a release into the folder, and return the program it contains (a binary or a macOS app).
    """
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if archive.name.endswith(('.tar.gz', '.tgz')):
            with tarfile.open(archive) as tar:
                tar.extractall(folder, filter='data')
        elif archive.suffix == '.zip' and sys.platform == 'darwin':  # Keeps the symbolic links of the app bundle
            subprocess.run(['ditto', '-x', '-k', str(archive), str(folder)], check=True, capture_output=True)
        elif archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as zip_file:
                zip_file.extractall(folder)
        else:
            raise UpdateError(f'Unknown archive format of {archive.name}')
    except (OSError, tarfile.TarError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        raise UpdateError(f'Unable to extract {archive.name}: {error}') from error

    content = [path for path in folder.iterdir() if path.name != '__MACOSX' and not path.name.startswith('.')]
    if len(content) != 1:
        raise UpdateError(f'Unexpected content in {archive.name}: {", ".join(path.name for path in content)}')

    program = content[0]
    if program.is_file():
        program.chmod(program.stat().st_mode | 0o755)  # Zip files do not keep the executable permission
    return program


def old_version_path(installed: Path) -> Path:
    return installed.with_name(installed.name + OLD_SUFFIX)


def _remove(path: Path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        with contextlib.suppress(OSError):
            path.unlink()


def replace(installed: Path, new: Path):
    """
    Put the new program in place of the installed one, which is renamed (it may be running). If the new program cannot
    be moved, the installed one is restored.
    """
    old = old_version_path(installed)
    _remove(old)  # From a previous update
    installed.rename(old)
    try:
        new.rename(installed)
    except OSError:
        old.rename(installed)
        raise


def remove_old_version(installed: Path | None = None):
    """
    Remove the previous version left by an update. It may still be running when the update starts the new one, so it
    is removed when the program starts next time. Nothing happens if it is still in use.
    """
    _remove(old_version_path(installed or installed_path()))


def install_update(release: Release, progress: Progress | None = None, installed: Path | None = None) -> Path:
    """
    Download the release and replace the installed program with it. Returns the path of the new program.
    """
    installed = installed or installed_path()
    folder = installed.parent
    if 'AppTranslocation' in folder.parts or not os.access(folder, os.W_OK):
        raise UpdateError(f'Unable to write in {folder}. Move {installed.name} to a folder of yours (e.g. '
                          'Applications on macOS) and try again, or download the new version from GitHub.')

    staging = folder / UPDATE_DIR
    shutil.rmtree(staging, ignore_errors=True)
    try:
        staging.mkdir()
        archive = download(release, staging, progress)
        new = extract(archive, staging / 'extracted')
        replace(installed, new)
    except OSError as error:
        raise UpdateError(f'Unable to install the new version in {folder}: {error}') from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return installed


def launch(program: Path):
    """
    Start the program in a new process, independent of this one (which usually exits right after).
    """
    environment = dict(os.environ)
    # A binary built with PyInstaller started from another one must not reuse its temporary folder, removed on exit
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    if 'LD_LIBRARY_PATH_ORIG' in environment:  # Linux: restore the library path changed by the PyInstaller bootloader
        environment['LD_LIBRARY_PATH'] = environment.pop('LD_LIBRARY_PATH_ORIG')
    else:
        environment.pop('LD_LIBRARY_PATH', None)

    command = ['open', '-n', str(program)] if program.suffix == '.app' else [str(program)]
    options: dict = {'start_new_session': True}
    if sys.platform == 'win32':
        options = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    subprocess.Popen(command, env=environment, cwd=program.parent, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **options)


def download_and_update(release: Release):
    """
    Update the command line program. It exits once updated, so it is run again with the new version.
    """
    console.info(f'Downloading arXiv-sorter {release.version} …', icon='⬇️')
    try:
        program = install_update(release)
    except UpdateError as error:
        console.error(f'{error}. Download it from {release.page or release.url}')
        return

    console.success(f'arXiv-sorter updated to {release.version} ({program}). Run it again to use the new version.')
    sys.exit()
