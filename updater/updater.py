import sys
from pathlib import Path
from platform import system
from time import sleep

import requests
from packaging import version

from app.dates_functions import current_utc_timestamp
from app.utils import timing_message

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


def check_for_update(platform: str, current_version: str, _verbose: bool = False) -> str | None:
    """
    Check in GitHub if there is a new version available, and return the download url of the asset for the platform.
    """
    try:
        while True:
            response = requests.get(URL, timeout=TIMEOUT)
            if response.status_code == 200:
                if _verbose:
                    print('The GitHub response for the latest release is:')
                    print(response.json(), '\n')
                break
            elif response.status_code in (403, 429):
                sleep(1)  # Wait 1 second and try again
                print('Too many requests to GitHub')
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = reset_time - int(current_utc_timestamp()) + 1
                if not 0 < wait_time <= MAX_WAIT:  # If the waiting time is too long (or unknown), exit
                    return None
                timing_message(wait_time, 'until next request to GitHub API ...')
            else:
                print(f'Unable to check for updates (GitHub status code {response.status_code})')
                return None

    except requests.RequestException:
        print('No internet connection')
        return None

    latest_version = response.json()['tag_name']

    if version.parse(f'v{current_version}') >= version.parse(latest_version):
        return None

    for asset in response.json()['assets']:
        if platform in asset['name']:
            return asset['browser_download_url']

    print(f'No asset found for {platform}')
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
    print(f'New version downloaded to {downloaded_path.resolve()}, replace the binary in {app_dir} with it.')

    sys.exit()
