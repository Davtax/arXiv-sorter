import os
import sys
from time import sleep
from platform import system
from subprocess import Popen
from typing import Union
import shutil
import zipfile

import requests
from packaging import version

from app.dates_functions import current_utc_timestamp
from app.utils import timing_message, question

URL = 'https://api.github.com/repos/Davtax/arXiv-sorter/releases/latest'


def get_system_name() -> str:
    if system() == 'Darwin':  # If macOS
        platform = 'macOS'
    elif system() == 'Windows':  # If Windows
        platform = 'Windows'
    elif system() == 'Linux':  # If Linux
        platform = 'Ubuntu'
    else:
        exit(f'Unknown platform {system()}')

    return platform


def check_for_update(platform: str, current_version: str, _verbose: bool = False) -> Union[None, str]:
    """
        Check in GitHub if there is a new version available.
    """

    try:
        while True:
            response = requests.get(URL)
            if response.status_code == 200:
                if _verbose:
                    print('The GitHub response for the latest release is:')
                    print(response.json(), '\n')
                break
            elif response.status_code == 403 or response.status_code == 429:
                sleep(1)  # Wait 1 second and try again
                print('Too many requests to GitHub')
                wait_time = int(response.headers['X-RateLimit-Reset']) - int(current_utc_timestamp()) + 1
                if wait_time > 10:  # If the waiting time is too long, exit
                    return None
                else:
                    timing_message(wait_time, 'until next request to GitHub API ...')

    except requests.ConnectionError:
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


def download_and_update(download_url):
    # Download the new version
    response = requests.get(download_url)
    filename = response.headers.get("Content-Disposition").split("filename=")[1]
    with open(f'temp_{filename}', 'wb') as f:
        f.write(response.content)

    # Extract the new version
    # with zipfile.ZipFile("temp.zip", "r") as zip_ref:
    #     zip_ref.extractall("temp")

    # Replace the old version with the new version
    app_dir = os.path.dirname(sys.executable)  # Get the directory where the script is running

    print(app_dir)

    sys.exit()

    shutil.rmtree(app_path)
    shutil.move(os.path.join("temp", "app"), app_path)

    # # Clean up temporary files  # os.remove("temp.zip")  # shutil.rmtree("temp")


def check_version(download_url: str, _verbose: bool = False):
    """
    Check in GitHub if there is a new version available. If so, download and execute it.
    """

    if '.py' not in sys.argv[0] and question('Do you want to update arXiv-sorter?'):
        os.rename(sys.argv[0], sys.argv[0] + '.old')

        response = requests.get(download_url)
        open(asset['name'], 'wb').write(response.content)

        print('The new version has been downloaded')
        Popen('./' + asset['name'])

        sys.exit()
