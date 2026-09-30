"""
Check of the search files (keywords.txt, authors.txt and categories.txt) before requesting arXiv, so a mistake is
reported with its file and line instead of stopping the sorting half way.
"""
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from unidecode import unidecode

# e.g. cond-mat, quant-ph, cond-mat.mes-hall, cs.LG, physics.atom-ph, q-bio.NC
CATEGORY_PATTERN = re.compile(r'^[a-z]+(-[a-z]+)?(\.[a-z]+(-[a-z]+)?)?$', re.IGNORECASE)


class Kind(StrEnum):
    KEYWORDS = 'keywords'
    AUTHORS = 'authors'
    CATEGORIES = 'categories'

    @property
    def filename(self) -> str:
        return f'{self.value}.txt'


class Severity(StrEnum):
    ERROR = 'error'  # The sorting would fail, or match everything
    WARNING = 'warning'  # Probably a mistake, but the run can go on


@dataclass(frozen=True)
class Problem:
    filename: str
    line: int  # 1-based
    text: str
    message: str
    severity: Severity = Severity.ERROR

    def __str__(self) -> str:
        return f'{self.filename}, line {self.line}: {self.message} ({self.text.strip()!r})'


def _search_pattern(term: str, kind: Kind) -> str:
    """
    Regular expression used by the sorting for the term (see user_files and pipeline).
    """
    term = unidecode(term.lower()).strip()
    return rf'\b{term}\b' if kind is Kind.AUTHORS else term


def _check_line(line: str, number: int, kind: Kind) -> list[Problem]:
    if kind is Kind.CATEGORIES:
        if CATEGORY_PATTERN.match(line.strip()):
            return []
        return [Problem(kind.filename, number, line, 'this does not look like an arXiv category (e.g. quant-ph, '
                        'cond-mat or cs.LG)', Severity.WARNING)]

    problems = []
    for term in line.split('&'):
        if not term.strip():
            problems.append(Problem(kind.filename, number, line, 'empty term next to "&", which would match every '
                                    'submission'))
            continue
        try:
            re.compile(_search_pattern(term, kind))
        except re.error as error:
            position = f' at position {error.pos}' if error.pos is not None else ''
            problems.append(Problem(kind.filename, number, term, f'invalid regular expression, {error.msg}{position}'))
    return problems


def check_lines(lines: list[str], kind: Kind) -> list[Problem]:
    """
    Problems of the lines of a search file. Empty lines and comments (#) are ignored.
    """
    return [problem for number, line in enumerate(lines, start=1)
            if line.strip() and not line.lstrip().startswith('#')
            for problem in _check_line(line, number, kind)]


def check_file(path: Path, kind: Kind) -> list[Problem]:
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []  # Missing files are created empty by the program
    return check_lines(lines, kind)


def check_folder(folder: Path) -> list[Problem]:
    """
    Problems of the three search files of the folder.
    """
    return [problem for kind in Kind for problem in check_file(folder / kind.filename, kind)]
