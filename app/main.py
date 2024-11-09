import argparse
import os
import sys
from datetime import datetime
from typing import List

from feedparser import FeedParserDict

from app.arXiv_api import search_entries
from app.dates_functions import check_last_date, next_mail, prev_mail
from app.format_entries import fix_entry, write_document
from app.pdf_scrapper import get_images_pdf_scrapper
from app.read_files import read_user_file
from app.sort_entries import sort_articles
from app.utils import question, timing_message
from updater.updater import check_for_update, download_and_update, get_system_name


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('-v', '--verbose', action='store_true', help='Increase output verbosity')

    parser.add_argument('-d', '--directory', help='Specify relative keywords directory (default = ./)', default='./')
    parser.add_argument('-a', '--abstracts', help='Specify abstracts directory (default = ./abstracts)',
                        default='./abstracts/')

    parser.add_argument('-t', '--time', help='Specify closing time in sec (default = 3s)', default=3, type=int)
    parser.add_argument('-f', '--final', action='store_false', help='Remove final date string in MarkDown file')
    parser.add_argument('-u', '--update', action='store_true', help='Update arXiv-sorter')
    parser.add_argument('-i', '--image', action='store_false', help='Remove images from abstracts')
    parser.add_argument('-s', '--separate', action='store_true', help='Separate each entry in a different file')
    parser.add_argument('-m', '--modify', action='store_false',
                        help='Dont modify the authors file (sort and remove blank lines)')

    parser.add_argument('--date0', help='Specify initial date (%Y%M%D)', default=None)
    parser.add_argument('--datef', help='Specify final date (%Y%M%D)', default=None)

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
    version = '0.2.1'
    print(f'Current arXiv-sorter version: v{version}')

    args = parse_args()

    current_dir = os.path.dirname(sys.argv[0])
    if current_dir != '':
        os.chdir(current_dir)  # Change working directory to script directory

    # Check internal usage folder exists
    TMP_FOLDER = '.arXiv_sorter'
    if not os.path.exists(TMP_FOLDER):
        os.mkdir(TMP_FOLDER)

    platform = get_system_name()
    new_version_url = check_for_update(platform, version, _verbose=args.verbose)
    if new_version_url is not None:
        print(f'New version available: {new_version_url}')
    if args.update and new_version_url is not None and question('Do you want to update arXiv-sorter?'):
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
    categories = read_user_file(keyword_dir + 'categories.txt')
    authors = read_user_file(keyword_dir + 'authors.txt', sort=True)
    authors = [r'\b' + author + r'\b' for author in authors]  # Convert list of authors to regex format

    if args.verbose:
        print('Keywords: ' + str(keywords))
        print('Authors: ' + str(authors))
        print('Categories: ' + str(categories) + '\n')

    # Search between last date with data and today
    if args.date0 is not None:
        date_0 = datetime.strptime(args.date0, '%Y%m%d')
    else:
        date_0 = check_last_date(args.abstracts, args.separate)

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

        for entries, date in zip(entries_dates, dates):  # Iterate over each day
            print('-' * n_bars)  # Length of previous message: 'Requesting arXiv ...'

            if len(entries) == 0:
                print(f'No entries found for {date.date()}')
                continue

            data_found = True

            [fix_entry(entry) for entry in entries]

            entries = sort_articles(entries, keywords, authors)

            # Get number of new manuscripts, and get their figure
            n_new = sum([1 for entry in entries if entry.index >= 0])

            print(f'Found {len(entries)} entries for {date.date()} ({n_new} new submissions or with matching keywords)')

            get_last_new(entries)

            if args.image:
                image_urls = get_images_pdf_scrapper(str(date.date()), entries[:n_new])
            else:
                image_urls = [None] * n_new

            write_document(entries, date, args.abstracts, args.final, args.separate, image_urls, version=version)
            print()

        # If data not found, search one day before previous date
        date_f = date_0
        date_0 = prev_mail(date_0)

    timing_message(args.time, 'before closing ...')
    clean_up()


if __name__ == '__main__':
    main()
