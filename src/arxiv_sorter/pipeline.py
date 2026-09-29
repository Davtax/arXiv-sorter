"""
Main workflow: request the new submissions, sort them by the user keywords, and write the Markdown files.
"""
import argparse
import os
import tempfile
from datetime import datetime
from pathlib import Path

from feedparser import FeedParserDict

from arxiv_sorter import __version__, console
from arxiv_sorter.arxiv_api import search_entries
from arxiv_sorter.console import report_written
from arxiv_sorter.dates import check_last_date, next_mail, prev_mail
from arxiv_sorter.figures import extract_figures
from arxiv_sorter.formatting import fix_entry, write_document
from arxiv_sorter.protocol import gui_mode
from arxiv_sorter.sorting import sort_articles
from arxiv_sorter.system import base_dir, is_frozen
from arxiv_sorter.updater import check_for_update, download_and_update, get_system_name
from arxiv_sorter.user_files import read_user_file


def get_last_new(entries: list[FeedParserDict]):
    """
    Flag the last new entry (the one before the first updated entry without matches), to separate both groups.
    """
    for i, entry in enumerate(entries):
        if entry['index'] == -1:
            if i > 0:
                entries[i - 1]['last_new'] = True
            break


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f'{count} {singular}' if count == 1 else f'{count} {plural or singular + "s"}'


def _day(date: datetime) -> str:
    return f'{date:%a} {date.day} {date:%b %Y}'  # e.g. Tue 22 Sep 2026


def _check_updates(args: argparse.Namespace):
    new_version_url = check_for_update(get_system_name(), __version__, gui=gui_mode())
    if new_version_url is None:
        return

    console.info(f'A new version of arXiv-sorter is available: {new_version_url}', icon='🆕')
    if args.update and console.question('Do you want to download the new version of arXiv-sorter?'):
        download_and_update(new_version_url)


def _read_search_files(args: argparse.Namespace, keyword_dir: Path) -> tuple[list[str], list[str], list[str]]:
    keywords = read_user_file(keyword_dir / 'keywords.txt')
    categories = read_user_file(keyword_dir / 'categories.txt')
    authors = read_user_file(keyword_dir / 'authors.txt', sort=args.modify)

    console.info(f'Searching {_plural(len(keywords), "keyword")}, {_plural(len(authors), "author")} and '
                 f'{_plural(len(categories), "category", "categories")} (from {keyword_dir.resolve()})', icon='🔑')
    if not categories:
        console.warning('categories.txt is empty, so the submissions of all the arXiv categories are requested')
    console.detail(f'Keywords: {", ".join(keywords) or "none"}')
    console.detail(f'Authors: {", ".join(authors) or "none"}')
    console.detail(f'Categories: {", ".join(categories) or "all"}')

    authors = [r'\b' + author + r'\b' for author in authors]  # Only full matches of the names
    return keywords, authors, categories


def _dates_to_request(args: argparse.Namespace, abstracts_dir: Path) -> tuple[datetime, datetime]:
    if args.date0 is not None:
        date_0 = datetime.strptime(args.date0, '%Y%m%d')
    else:
        last_date = check_last_date(abstracts_dir, args.separate)
        if last_date is None:
            console.detail('No previous abstracts found, starting from the last mailing list')
            date_0 = prev_mail(datetime.now())
        else:
            console.detail(f'Last abstracts saved: {_day(last_date)}')
            date_0 = next_mail(last_date)

    date_f = datetime.strptime(args.datef, '%Y%m%d') if args.datef is not None else datetime.now()
    return date_0, date_f


def run(args: argparse.Namespace, temp_dir: tempfile.TemporaryDirectory):
    console.set_verbose(args.verbose)
    console.step(f'arXiv-sorter v{__version__}', icon='📚')

    if is_frozen():  # Relative paths are next to the binary, wherever it is launched from
        os.chdir(base_dir())
    console.detail(f'Working directory: {Path.cwd()}')

    _check_updates(args)

    keyword_dir = Path(args.directory)
    abstracts_dir = Path(args.abstracts)
    keyword_dir.mkdir(parents=True, exist_ok=True)
    abstracts_dir.mkdir(parents=True, exist_ok=True)

    keywords, authors, categories = _read_search_files(args, keyword_dir)
    console.info(f'Abstracts are saved in {abstracts_dir.resolve()}', icon='💾')
    if args.image:
        console.detail(f'Figures detected with {_plural(args.threads, "thread")}')
    else:
        console.detail('Figures disabled (--image)')

    date_0, date_f = _dates_to_request(args, abstracts_dir)

    data_found = False
    while not data_found:  # Keep searching until data is found
        console.step(f'Requesting the submissions from {_day(date_0)} to {_day(date_f)}', icon='📡')

        entries_dates, dates = search_entries(categories, date_0, date_f)

        for entries, date in zip(entries_dates, dates, strict=True):  # Iterate over each day
            if len(entries) == 0:
                console.info(f'No submissions in the mailing list of {_day(date)}', icon='📭')
                continue

            data_found = True
            console.step(f'Mailing list of {_day(date)}', icon='📅')

            for entry in entries:
                try:
                    fix_entry(entry)
                except IndexError as error:
                    console.warning(f'Unable to format the entry {entry.id} ({error}), it is kept as it is')

            entries = sort_articles(entries, keywords, authors)
            n_new = sum(1 for entry in entries if entry.index >= 0)  # New submissions, or with matching keywords
            console.info(f'{_plural(len(entries), "entry", "entries")}, {n_new} of them new or matching your '
                         'keywords', icon='📄')

            get_last_new(entries)

            if args.image:
                image_urls = extract_figures(
                    str(date.date()), entries[:n_new], temp_dir, abstracts_dir, args.separate, threads=args.threads
                )
            else:
                image_urls = [None] * n_new

            path = write_document(entries, date, abstracts_dir, args.final, args.separate, image_urls,
                                  version=__version__)
            report_written(path, len(entries), n_new)
            console.success(f'Saved {path.name}', icon='💾')

        if not data_found:  # Search one mailing list before the previous date
            console.info('Nothing new yet, looking one mailing list earlier', icon='🔙')
        date_f = date_0
        date_0 = prev_mail(date_0)
