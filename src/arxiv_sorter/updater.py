import sys
from pathlib import Path
from platform import system
from time import sleep

import requests
from packaging import version

from arxiv_sorter import console
from arxiv_sorter.console import timing_message
from arxiv_sorter.dates import current_utc_timestamp

URL = 'https://api.github.com/repos/Davtax/arXiv-sorter/releases/latest'
TIMEOUT = 10  # seconds
MAX_WAIT = 10  # maximum seconds to wait for the GitHub rate limit to reset

PLATFORMS = {'Darwin': 'macOS', 'Windows': 'Windows', 'Linux': 'Ubuntu'}


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
    Name (without extension) of the release asset for the platform, e.g. arXiv-sorter-Windows or arXiv-sorter-GUI-macOS.
    """
    return f'arXiv-sorter-GUI-{platform}' if gui else f'arXiv-sorter-{platform}'


def check_for_update(platform: str, current_version: str, gui: bool = False) -> str | None:
    """
    Check in GitHub if there is a new version available, and return the download url of the asset for the platform
    (of the GUI or of the command line program).
    """
    try:
        while True:
            response = requests.get(URL, timeout=TIMEOUT)
            if response.status_code == 200:
                break
            elif response.status_code in (403, 429):
                sleep(1)  # Wait 1 second and try again
                console.detail('Too many requests to GitHub, waiting to check for updates')
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = reset_time - int(current_utc_timestamp()) + 1
                if not 0 < wait_time <= MAX_WAIT:  # If the waiting time is too long (or unknown), exit
                    return None
                timing_message(wait_time, 'until the next request to GitHub …')
            else:
                console.detail(f'Unable to check for updates (GitHub status code {response.status_code})')
                return None

    except requests.RequestException:
        console.warning('No internet connection, unable to check for updates', icon='🌐')
        return None

    latest_version = response.json()['tag_name']
    console.detail(f'Latest release on GitHub: {latest_version} (this is v{current_version})')

    if version.parse(f'v{current_version}') >= version.parse(latest_version):
        return None

    name = asset_name(platform, gui)
    for asset in response.json()['assets']:
        if asset['name'].split('.')[0] == name:  # The extension depends on the platform (.zip, .tar.gz)
            return asset['browser_download_url']

    console.detail(f'No asset {name} found in the latest release')
    return None


def download_and_update(download_url: str):
    """
    Download the new version next to the current one.
    TODO: replace the running binary with the downloaded one, the program exits after the download for now.
    """
    response = requests.get(download_url, timeout=TIMEOUT)
    filename = response.headers.get("Content-Disposition").split("filename=")[1]
    downloaded_path = Path(f'temp_{filename}')
    downloaded_path.write_bytes(response.content)

    app_dir = Path(sys.executable).resolve().parent  # Get the directory where the script is running
    console.success(f'New version downloaded to {downloaded_path.resolve()}. Replace the program in {app_dir} with it.')

    sys.exit()
