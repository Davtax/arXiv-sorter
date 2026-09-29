"""
Check that the version of the program is larger than the one in main (used by the tests workflow in the pull requests).

Usage: python scripts/version_bumped.py <__init__.py of main> <__init__.py of the pull request>
"""
import re
import sys
from pathlib import Path

from packaging import version


def read_version(name: str) -> version.Version:
    match = re.search(r'^__version__ = "(.*)"', Path(name).read_text(encoding='utf-8'), re.MULTILINE)
    if match is None:
        raise ValueError(f'No __version__ found in {name}')
    return version.parse(match.group(1))


def main(names: list[str]) -> int:
    if len(names) != 2:
        print(__doc__)
        return 2

    main_version, new_version = (read_version(name) for name in names)
    if new_version <= main_version:
        print(f'::error::The version {new_version} must be larger than the version {main_version} in main')
        return 1

    print(f'The version {new_version} is larger than the version {main_version} in main')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
