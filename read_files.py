from unidecode import unidecode
from typing import List
import os


def read_user_file(file_name: str) -> List[str]:
    if not os.path.exists(file_name):
        open(file_name, 'x').close()

    with open(file_name, 'r', encoding='utf-8') as f:
        lines = f.read()

    lines = lines.split('\n')

    unique_lines = []
    for i in range(len(lines)):
        line = unidecode(lines[i].lower()).strip()  # Normalize unicode characters (e.g. accents) and remove spaces

        if line:  # Line is not empty
            if line[0] == '#':
                continue
            else:
                multiple_keywords = line.split(' + ')

                if len(multiple_keywords) > 1:
                    unique_lines.append(multiple_keywords)
                else:
                    if line not in unique_lines:
                        unique_lines.append(line)

    return unique_lines
