"""
Search files of the user (keywords, authors and categories), summarized in the window.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchFile:
    filename: str
    singular: str
    plural: str
    icon: str


SEARCH_FILES = (
    SearchFile('keywords.txt', 'keyword', 'keywords', '🔑'),
    SearchFile('authors.txt', 'author', 'authors', '👤'),
    SearchFile('categories.txt', 'category', 'categories', '🏷'),
)


def count_terms(path: Path) -> int | None:
    """
    Number of search terms in the file (non-empty lines that are not commented with #), or None if it does not exist.
    """
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    return sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#'))


def describe(search_file: SearchFile, count: int | None) -> str:
    """
    e.g. '🔑 4 keywords', '🏷 all categories' (an empty categories file requests all of them), '👤 no authors'.
    """
    if count is None or count == 0:
        amount = f'all {search_file.plural}' if search_file.filename == 'categories.txt' else f'no {search_file.plural}'
    else:
        amount = f'{count} {search_file.singular if count == 1 else search_file.plural}'
    return f'{search_file.icon} {amount}'
