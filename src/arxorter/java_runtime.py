"""
Java runtime that runs pdffigures2: the one installed in the system or, when there is none, a Java runtime (Eclipse
Temurin) downloaded the first time and kept in the configuration folder, so the users do not need to install Java.
"""
import hashlib
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from subprocess import run

import requests

from arxorter import console
from arxorter.console import Progressbar
from arxorter.system import NO_WINDOW, config_dir

JAVA_VERSION = 21  # Long term support
# Kept next to pdffigures2, so it persists when the program is moved or updated
RUNTIME_DIR = config_dir() / 'java'
ADOPTIUM_URL = f'https://api.adoptium.net/v3/assets/latest/{JAVA_VERSION}/hotspot'
# Names of the systems and architectures in the Adoptium API
OS_NAMES = {'win32': 'windows', 'darwin': 'mac', 'linux': 'linux'}
ARCHITECTURES = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}
TIMEOUT = 60
MB = 1024 ** 2


def downloaded_java() -> Path | None:
    """
    The java executable of the runtime downloaded previously, if any. The archive contains a single folder (e.g.
    jdk-21.0.8+9-jre), with the executable in bin/ (Contents/Home/bin/ on macOS).
    """
    name = 'java.exe' if sys.platform == 'win32' else 'java'
    for pattern in (f'*/bin/{name}', f'*/Contents/Home/bin/{name}'):
        java = next(RUNTIME_DIR.glob(pattern), None)
        if java is not None and java.is_file():
            return java
    return None


def system_java() -> bool:
    # Check if java is installed in the system
    try:
        run(['java', '-version'], capture_output=True, creationflags=NO_WINDOW)
        return True
    except OSError:
        return False


def find_java() -> str | Path | None:
    """
    The java executable to run pdffigures2: the runtime downloaded previously, the one of the system, or a runtime
    downloaded now (only the first time). None if there is none, so the figures are skipped.
    """
    java = downloaded_java()
    if java is not None:
        return java
    if system_java():
        return 'java'
    return download_java()


def runtime_package() -> dict | None:
    """
    Description of the Java runtime for this system in the Adoptium API: its name, link, size and SHA-256 checksum. None
    if there is no runtime for this system.
    """
    os_name = OS_NAMES.get(sys.platform)
    architecture = ARCHITECTURES.get(platform.machine().lower())
    if os_name is None or architecture is None:
        return None

    response = requests.get(ADOPTIUM_URL, params={'os': os_name, 'architecture': architecture, 'image_type': 'jre',
                                                  'vendor': 'eclipse'}, timeout=TIMEOUT)
    response.raise_for_status()
    releases = response.json()
    return releases[0]['binary']['package'] if releases else None


def _download(package: dict, path: Path) -> None:
    """
    Download the package into the path, showing the progress in MB, and verify its checksum.
    """
    n_mb = max(package['size'] // MB, 1)
    pbar = Progressbar(n_mb, prefix='Downloading Java (MB)', icon='📥')
    checksum = hashlib.sha256()
    received = shown = 0
    with requests.get(package['link'], stream=True, timeout=TIMEOUT) as response, path.open('wb') as file:
        response.raise_for_status()
        for chunk in response.iter_content(MB):
            file.write(chunk)
            checksum.update(chunk)
            received += len(chunk)
            done = min(received // MB, n_mb)
            if done > shown:
                pbar.update(done - shown)
                shown = done
    pbar.close()

    if checksum.hexdigest() != package['checksum'].lower():
        raise ValueError('the download is corrupted, its checksum does not match')


def _extract(archive: Path, folder: Path) -> None:
    # A .zip file on Windows, a .tar.gz file elsewhere (which keeps the executable permission and the symbolic links)
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(folder)
    else:
        with tarfile.open(archive) as tar:
            tar.extractall(folder, filter='data')


def download_java() -> Path | None:
    """
    Download the Java runtime into the configuration folder, and return its java executable (None if it failed).
    """
    console.info('Java is not installed, so a Java runtime is downloaded (about 50 MB) to detect the figures. It is '
                 'only needed the first time …', icon='📦')
    failure = 'Running without figure detection. Install Java from https://adoptium.net to include them.'
    try:
        package = runtime_package()
        if package is None:
            console.warning(f'There is no Java runtime to download for this system. {failure}')
            return None

        RUNTIME_DIR.parent.mkdir(parents=True, exist_ok=True)
        # Downloaded and extracted next to its final location first, so an interrupted download leaves nothing behind
        with tempfile.TemporaryDirectory(prefix='java-', dir=RUNTIME_DIR.parent, ignore_cleanup_errors=True) as tmp:
            archive = Path(tmp) / package['name']
            extracted = Path(tmp) / 'java'
            _download(package, archive)
            _extract(archive, extracted)
            shutil.rmtree(RUNTIME_DIR, ignore_errors=True)  # A broken runtime, without java executable
            os.replace(extracted, RUNTIME_DIR)
    except (requests.RequestException, OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile) as error:
        console.warning(f'Unable to download Java ({error}). {failure}')
        return None

    java = downloaded_java()
    if java is None:
        console.warning(f'The Java runtime downloaded in {RUNTIME_DIR} has no java executable. {failure}')
        return None

    console.success(f'Java saved in {RUNTIME_DIR}')
    return java
