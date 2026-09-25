import re
from datetime import datetime
from pathlib import Path
from typing import TextIO

from feedparser import FeedParserDict

from app.dates_functions import obtain_date

# Note: fields are always assigned with `entry[key] = value`. FeedParserDict only redirects attribute *reads* to the
# dictionary, so `entry.key = value` would create a shadowing attribute and leave the dictionary item outdated.


def _remove_white_spaces(text: str) -> str:
    """
    Remove duplicate white spaces from a string.
    """
    return re.sub(' {2,}', ' ', text)


def _clean_text(text: str) -> str:
    """
    Remove line breaks, duplicate white spaces and backticks, which break the markdown format.
    """
    text = text.replace('\n', ' ')  # The raw data contains carriage returns
    text = _remove_white_spaces(text)
    return text.replace('`', "'")


def _fix_title(entry: FeedParserDict):
    """
    Fix the title to remove white spaces and other uncommon characters.
    """
    title = _clean_text(entry.title)

    entry['updated_bool'] = entry.updated != entry.published  # If the entry has been updated, so it is not new
    if entry.updated_bool:
        title += ' *(UPDATED)*'

    entry['title'] = title


def _fix_abstract(entry: FeedParserDict):
    """
    Fix the abstract to remove white spaces and other uncommon characters.
    """
    entry['summary'] = _clean_text(entry.summary)


def _fix_authors(entry: FeedParserDict):
    """
    Join the authors in a single string.
    """
    entry['authors'] = ', '.join(author.name for author in entry.authors)


def _fix_equation_inner(text: str) -> str:
    """
    Fix the equations to proper visualization in the markdown file.
    """
    index_0 = text.find('$')  # Find the beginning equation
    while index_0 != -1:
        try:
            if text[index_0 + 1] == ' ':  # Remove the white space after the first $
                text = text[:index_0 + 1] + text[index_0 + 2:]
        except IndexError:
            break

        index_1 = text.find('$', index_0 + 1)  # Find the end of the equation
        if index_1 == -1:
            break

        if text[index_1 - 1] == ' ':  # Remove the white space before the end of the equation
            text = text[:index_1 - 1] + text[index_1:]
            index_1 += -1

        try:
            if text[index_1 + 1].isnumeric():  # Add a white space after the end of the equation if there is a number
                text = text[:index_1 + 1] + ' ' + text[index_1 + 1:]
        except IndexError:
            pass

        index_0 = text.find('$', index_1 + 1)  # Find the beginning of the next equation

    # Replace common HTML characters which are not supported by markdown
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')

    text = _remove_white_spaces(text)
    return text


def _fix_equations(entry: FeedParserDict):
    """
    Fix the equations that appear both in the title and the abstract.
    """
    entry['summary'] = _fix_equation_inner(entry.summary)
    entry['title'] = _fix_equation_inner(entry.title)


def _fix_date(entry: FeedParserDict):
    """
    Fix the date to the proper format.
    """
    entry['updated'] = obtain_date(entry.updated).strftime("%a, %d %b %Y %H:%M:%S GMT")


def fix_entry(entry: FeedParserDict):
    """
    Fix the entry to proper visualization in the markdown file.
    """
    _fix_title(entry)
    _fix_abstract(entry)
    _fix_authors(entry)
    _fix_equations(entry)
    _fix_date(entry)


def write_article(entry: FeedParserDict, f: TextIO, index: int, n_total: int, image_url: str | None = None):
    """
    Write the article to the markdown file. `index` is zero-based.
    """
    f.write(f'({index + 1} / {n_total})\n\n')
    f.write(f'Title: **{entry.title}**\n\n')

    if ',' in entry.authors:
        f.write(f'Authors: {entry.authors}\n\n')
    else:
        f.write(f'Author: {entry.authors}\n\n')

    if image_url is not None:
        f.write(f"<img src='{image_url}' align='right'  width='300' class='arXiv-sorter'>\n\n")

    f.write(f'Abstract: {entry.summary}\n\n')
    f.write(f'{entry.id}\n\n')
    f.write(f'<span style="font-size:0.9em;">*Updated: {entry.updated}*</span>\n\n')
    f.write('---\n')

    if entry.last_new:
        f.write('\n---\n')


def write_document(entries: list[FeedParserDict], date: datetime, abstracts_dir: str | Path, final: bool,
                   separate_files: bool, image_urls: list[str | None], version: str | None = None):
    """
    Write the sorted entries of a given date, either in a single markdown file or in a folder with a file per entry.
    `image_urls` contains the figure of each new entry (index >= 0), which are placed at the beginning of `entries`.
    """
    print('Writing entries ...')

    abstracts_path = Path(abstracts_dir)
    if separate_files:
        root = abstracts_path / str(date.date())
        root.mkdir(parents=True, exist_ok=True)

        _write_document_split(root, entries, image_urls)
    else:
        file_name = abstracts_path / f'{date.date()}.md'
        _write_document_join(file_name, entries, image_urls, final, version)


def _count_new(entries: list[FeedParserDict]) -> int:
    return sum(1 for entry in entries if entry.index >= 0)


def _write_document_join(file_name: Path, entries: list[FeedParserDict], image_urls: list[str | None], final: bool,
                         version: str | None):
    n_new = _count_new(entries)
    new_entries, updated_entries = entries[:n_new], entries[n_new:]

    with file_name.open('w', encoding='utf-8') as f:
        for i, entry in enumerate(new_entries):  # New articles (or with a matching keyword)
            write_article(entry, f, i, n_new, image_url=image_urls[i])

        for i, entry in enumerate(updated_entries):
            write_article(entry, f, i, len(updated_entries))

        if final:
            msg = f'\n*This file was created at: {datetime.now().strftime("%d %B %Y %H:%M:%S")}'
            if version is not None:
                msg += f', with arXiv-sorter version: {version}'
            f.write(msg + '*')


def _write_document_split(root: Path, entries: list[FeedParserDict], image_urls: list[str | None]):
    n_new = _count_new(entries)
    new_entries, updated_entries = entries[:n_new], entries[n_new:]

    def file_name(position: int, entry: FeedParserDict) -> Path:
        return root / f"{position}_{entry.id.split('/')[-1]}.md"

    for i, entry in enumerate(new_entries):
        with file_name(i, entry).open('w', encoding='utf-8') as f:
            write_article(entry, f, i, n_new, image_url=image_urls[i])

    for i, entry in enumerate(updated_entries):
        with file_name(n_new + i, entry).open('w', encoding='utf-8') as f:
            write_article(entry, f, i, len(updated_entries))
