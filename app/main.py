import argparse
import os
import sys
from datetime import datetime

from feedparser import FeedParserDict
from typing import List

from app.arXiv_api import search_entries
from app.dates_functions import check_last_date, shift_date
from app.format_entries import write_document, fix_entry
from app.read_files import read_user_file
from app.sort_entries import sort_articles
from app.utils import timing_message, question
from updater.updater import get_system_name, check_for_update, download_and_update


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('-v', '--verbose', action='store_true', help='increase output verbosity')
    parser.add_argument('-d', '--directory', help='specify relative keywords directory', default='./')
    parser.add_argument('-t', '--time', help='specify closing time', default=3, type=int)
    parser.add_argument('-f', '--final', action='store_false', help='remove final date string in MarkDown file')
    parser.add_argument('-a', '--abstracts', help='specify abstracts directory', default='./abstracts/')
    parser.add_argument('-u', '--update', action='store_true', help='avoid update arXiv-sorter')

    args = parser.parse_args()
    return args


def get_last_new(entries: List[FeedParserDict]):
    for i, entry in enumerate(entries):
        if entry['index'] == -1:
            entries[i - 1]['last_new'] = True
            break


def clean_up():
    # Remove files from previous version
    for file in os.listdir():
        if '.old' in file:
            print(f'Removing {file}')
            os.remove(file)


def main():
    version = '0.0.9'
    print(f'Current arXiv-sorter version: v{version}')

    args = parse_args()

    current_dir = os.path.dirname(sys.argv[0])
    if current_dir != '':
        os.chdir(current_dir)  # Change working directory to script directory

    platform = get_system_name()
    if args.update:
        new_version_url = check_for_update(platform, version, _verbose=args.verbose)
        if new_version_url is not None and question('Do you want to update arXiv-sorter?'):
            download_and_update(new_version_url)

    keyword_dir = args.directory
    if keyword_dir[-1] != '/':
        keyword_dir += '/'

    if args.abstracts[-1] != '/':
        args.abstracts += '/'

    if not os.path.isdir(keyword_dir):
        os.mkdir(keyword_dir)  # Create dir if it doesn't exist

    if not os.path.exists(args.abstracts):  # Create folder for abstracts if it doesn't exist
        os.mkdir(args.abstracts)

    if args.verbose:
        print(f'The current dir is: {os.getcwd()}, and the keywords dir is: {keyword_dir} \n')

    # Read user files
    keywords = read_user_file(keyword_dir + 'keywords.txt')
    authors = read_user_file(keyword_dir + 'authors.txt', sort=True, name_separator=True)
    categories = read_user_file(keyword_dir + 'categories.txt', sort=True)

    if args.verbose:
        print('Keywords: ' + str(keywords))
        print('Authors: ' + str(authors))
        print('Categories: ' + str(categories) + '\n')

    # Search between last date with data and today
    date_0 = shift_date(check_last_date(), 1)  # Search one day after last date with data
    date_f = datetime.now()

    data_found = False
    while not data_found:  # Keep searching until data is found
        print('\nRequesting arXiv API feed between ' + str(date_0.date()) + ' and ' + str(date_f.date()))

        entries_dates, dates = search_entries(categories, date_0, date_f, _verbose=args.verbose)
        for entries, date in zip(entries_dates, dates):  # Iterate over each day
            if len(entries) == 0:
                print(f'No entries found for {date.date()}')
                continue

            data_found = True
            print(f'Found {len(entries)} entries for {date.date()}')

            print('Formatting entries...')
            [fix_entry(entry) for entry in entries]

            print('Sorting entries...')
            entries = sort_articles(entries, keywords, authors)

            get_last_new(entries)

            write_document(entries, date, args.abstracts, args.final)
            print()

        # If data not found, search one day before previous date
        date_f = date_0
        date_0 = shift_date(date_0, -1)

    timing_message(args.time, 'before closing ...')
    clean_up()


if __name__ == '__main__':
    main()
