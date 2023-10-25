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

    if sort:  # Sort the data in the user file by alphabetical order
        lines.sort()

        with open(file_name, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    lines = [line for line in lines if line]  # Remove empty lines
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

        multiple_keywords = line.split(' + ')  # Split the concatenated keywords

        if len(multiple_keywords) == 1:
            multiple_keywords = multiple_keywords[0]

        if multiple_keywords not in unique_lines:
            unique_lines.append(multiple_keywords)

    return unique_lines
