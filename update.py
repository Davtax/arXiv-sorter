import os
import sys
from platform import system
from subprocess import Popen
from time import sleep

import requests
from packaging import version

URL = 'https://api.github.com/repos/Davtax/arXiv-sorter/releases/latest'


def question(message) -> bool:
    """
    Make a question and return True or False depending on the answer of the user. There is only two possible answers
    y -> yes or	n -> no. If the answer is none of this two the question is repeated until a good answer is given.
    If not message is provided, then the default overwriting file message is printed, with the file name provided.
    """
    temp = input(message + '  [y]/n: ').lower()  # Ask for an answer by keyword input

    if temp == 'y' or temp == '':
        return True
    elif temp == 'n':
        return False
    else:  # If the answer is not correct
        print('I didn\'t understand your answer.')
        return question(message)  # The function will repeat until a correct answer if provided


def get_system_name() -> str:
    if system() == 'Darwin':  # If macOS
        platform = 'mac'
    elif system() == 'Windows':  # If Windows
        platform = 'windows'
    elif system() == 'Linux':  # If Linux
        platform = 'linux'
    else:
        exit(f'Unknown platform {system()}')

    return platform


def check_version(previous_version: str, _verbose: bool = False):
    """
    Check in GitHub if there is a new version available. If so, download and execute it.
    """
    while True:
        response = requests.get(URL)
        if response.status_code == 200:
            break
        elif response.status_code == 403 or response.status_code == 429:
            print('Too many requests to GitHub, waiting 30 seconds')
            sleep(30)

    platform = get_system_name()

    if _verbose:
        print('The GitHub response for the latest release is:')
        print(response.json())

    new_version = response.json()['tag_name']

    if version.parse(previous_version) < version.parse(new_version):
        print('New version available: ' + new_version)

        if '.py' not in sys.argv[0] and question('Do you want to update arXiv-sorter?'):
            os.rename(sys.argv[0], sys.argv[0] + '.old')

            for asset in response.json()['assets']:
                if platform in asset['name']:
                    response = requests.get(asset['browser_download_url'])
                    open(asset['name'], 'wb').write(response.content)

                    print('The new version has been downloaded')
                    Popen('./' + asset['name'])

                    sys.exit()
