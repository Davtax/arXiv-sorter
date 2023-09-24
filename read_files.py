from unidecode import unidecode
from typing import List


def read_user_file(file_name: str) -> List[str]:
    with open(file_name, 'r') as f:
        lines = f.read()

    lines = lines.split('\n')

    unique_lines = []
    for i in range(len(lines)):
        line = unidecode(lines[i].lower())  # Normalize unicode characters (e.g. accents)

        if len(line) == 0:
            continue
        elif line[0] == '#':
            continue
        else:
            if line not in unique_lines:
                unique_lines.append(line)

    return unique_lines
