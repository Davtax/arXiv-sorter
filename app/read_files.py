from pathlib import Path

from unidecode import unidecode


def read_user_file(file_name: str | Path, sort: bool = False) -> list[str]:
    """
    Read a file with keywords or authors and return a list of unique lines.
    """
    file_path = Path(file_name)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.touch(exist_ok=True)

    lines = file_path.read_text(encoding='utf-8').splitlines()
    lines = [line for line in lines if line.strip()]  # Remove empty lines

    if sort:
        lines = sorted(lines, key=_sorting_key)
        file_path.write_text(''.join(f'{line}\n' for line in lines), encoding='utf-8')

    lines = [line for line in lines if not line.lstrip().startswith('#')]  # Remove comments

    return _obtain_unique_lines(lines)


def _obtain_unique_lines(lines: list[str]) -> list[str]:
    """
    Obtain the unique lines from a list of lines, after a normalization process (lower case, no accents and no
    surrounding spaces).
    """
    unique_lines = []
    for line in lines:
        line = unidecode(line.lower()).strip()

        if line not in unique_lines:
            unique_lines.append(line)

    return unique_lines


def _sorting_key(name: str) -> str:
    # Sort by the second element of the name, if it exists
    try:
        return name.split('+')[1]
    except IndexError:
        return name
