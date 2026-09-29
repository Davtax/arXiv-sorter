"""
Main workflow: request the new submissions, sort them by the user keywords, and write the Markdown files.
"""
import argparse
import os
import tempfile
from datetime import datetime
from pathlib import Path

from feedparser import FeedParserDict

from arxiv_sorter import __version__
from arxiv_sorter.arxiv_api import search_entries
from arxiv_sorter.console import question, report_written
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


def run(args: argparse.Namespace, temp_dir: tempfile.TemporaryDirectory):
    print(f'Current arXiv-sorter version: v{__version__}')

    if is_frozen():  # Relative paths are next to the binary, wherever it is launched from
        os.chdir(base_dir())

    # Check updates of arXiv-sorter
    platform = get_system_name()
    new_version_url = check_for_update(platform, __version__, gui=gui_mode(), _verbose=args.verbose)
    if new_version_url is not None:
        print(f'New version available: {new_version_url}')
    if args.update and new_version_url is not None and question('Do you want to update arXiv-sorter?'):
        download_and_update(new_version_url)

    keyword_dir = Path(args.directory)
    abstracts_dir = Path(args.abstracts)
    keyword_dir.mkdir(parents=True, exist_ok=True)
    abstracts_dir.mkdir(parents=True, exist_ok=True)

    if args.verbose:
        print(f'The current dir is: {Path.cwd()}, and the keywords dir is: {keyword_dir} \n')

    # Read user files
    keywords = read_user_file(keyword_dir / 'keywords.txt')
    categories = read_user_file(keyword_dir / 'categories.txt')
    authors = read_user_file(keyword_dir / 'authors.txt', sort=args.modify)
    authors = [r'\b' + author + r'\b' for author in authors]  # Convert list of authors to regex format

    if args.verbose:
        print('Keywords: ' + str(keywords))
        print('Authors: ' + str(authors))
        print('Categories: ' + str(categories))
        if args.image:
            print(f'Threads to detect the figures: {args.threads}')
        print()

    # Search between last date with data and today
    if args.date0 is not None:
        date_0 = datetime.strptime(args.date0, '%Y%m%d')
    else:
        date_0 = check_last_date(abstracts_dir, args.separate)

        if date_0 is None:
            date_0 = prev_mail(datetime.now())
        else:
            date_0 = next_mail(date_0)

    if args.datef is not None:
        date_f = datetime.strptime(args.datef, '%Y%m%d')
    else:
        date_f = datetime.now()

    data_found = False
    while not data_found:  # Keep searching until data is found
        print('\nRequesting arXiv API feed between ' + str(date_0.date()) + ' and ' + str(date_f.date()))

        entries_dates, dates = search_entries(categories, date_0, date_f, _verbose=args.verbose)

        sentence_len = 59
        try:
            terminal_size = os.get_terminal_size().columns
            n_bars = min(terminal_size, sentence_len)
        except OSError:
            n_bars = sentence_len

        for entries, date in zip(entries_dates, dates, strict=True):  # Iterate over each day
            print('-' * n_bars)  # Length of previous message: 'Requesting arXiv ...'

            if len(entries) == 0:
                print(f'No entries found for {date.date()}')
                continue

            data_found = True

            for entry in entries:
                try:
                    fix_entry(entry)
                except IndexError as error:
                    print(f'Error formatting the entry {entry.id}: {error}')

            entries = sort_articles(entries, keywords, authors)

            # Get number of new manuscripts, and get their figure
            n_new = sum(1 for entry in entries if entry.index >= 0)

            print(f'Found {len(entries)} entries for {date.date()} ({n_new} new submissions or with matching keywords)')

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
            print()

        # If data not found, search one day before previous date
        date_f = date_0
        date_0 = prev_mail(date_0)
