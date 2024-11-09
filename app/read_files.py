from unidecode import unidecode
from typing import List
import os


def read_user_file(file_name: str, sort: bool = False) -> List[str]:
    """
    Read a file with keywords or authors and return a list of unique lines.
    """
    if not os.path.exists(file_name):
        open(file_name, 'x').close()  # Create file if it doesn't exist

    with open(file_name, 'r', encoding='utf-8') as f:
        lines = f.read()

    lines = lines.split('\n')
    lines = [line for line in lines if line]  # Remove empty lines

    if sort:
        lines = sorted(lines, key=_sorting_key)

        with open(file_name, 'w', encoding='utf-8') as f:
            [f.write(line + '\n') for line in lines]

    lines = [line for line in lines if line[0] != '#']  # Remove comments

    return _obtain_unique_lines(lines)


def _obtain_unique_lines(lines: List[str]) -> List[str]:
    """
    Obtain the unique lines from a list of lines, after a normalization process. If multiple keywords are present, then
    they are grouped together in a list.
    """
    unique_lines = []
    for i in range(len(lines)):
        line = unidecode(lines[i].lower()).strip()  # Normalize unicode characters (e.g. accents) and remove spaces

        if line not in unique_lines:
            unique_lines.append(line)

    return unique_lines


def _sorting_key(name: str) -> str:
    # Sort by the second element of the name, if it exists
    try:
        return name.split('+')[1]
    except IndexError:
        return name
