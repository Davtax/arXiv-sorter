import argparse
import os
import sys
from datetime import datetime, timedelta
from time import sleep

from arXiv_api import search_entries
from dates_functions import check_last_date
from format_entries import fix_entry, write_article
from read_files import read_user_file
from sort_entries import sort_articles
from update import check_version

version = '0.0.6'

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='store_true', help='increase output verbosity')
parser.add_argument('-d', '--directory', help='specify relative keywords directory', default='./')
parser.add_argument('-t', '--time', help='specify closing time', default=3, type=int)
parser.add_argument('-f', '--final', action='store_false', help='remove final date string in MarkDown file')
args = parser.parse_args()

verbose = args.verbose
keyword_dir = args.directory
if keyword_dir[-1] != '/':
    keyword_dir += '/'

current_dir = os.path.dirname(sys.argv[0])

if current_dir != '':
    os.chdir(current_dir)  # Change working directory to script directory

check_version(version, _verbose=verbose)

if not os.path.isdir(keyword_dir):
    os.mkdir(keyword_dir)  # Create dir if it doesn't exist

if verbose:
    print(f'The current dir is: {os.getcwd()}, and the keywords dir is: {keyword_dir}')

# Read user files
keywords = read_user_file(keyword_dir + 'keywords.txt')
authors = read_user_file(keyword_dir + 'authors.txt', sort=True)
categories = read_user_file(keyword_dir + 'categories.txt', sort=True)

if verbose:
    print('Keywords: ' + str(keywords))
    print('Authors: ' + str(authors))
    print('Categories: ' + str(categories) + '\n')

if not os.path.exists('abstracts'):  # Create folder for abstracts if it doesn't exist
    os.mkdir('abstracts')

# Search between last date with data and today
date_0 = check_last_date() + timedelta(days=1)
if date_0.weekday() > 4:  # If date_0 is a weekend, search from Monday
    date_0 += timedelta(days=7 - date_0.weekday())

date_f = datetime.now()

data_found = False
while not data_found:  # Keep searching until data is found
    # print('\n')
    print('Requesting arXiv API feed between ' + str(date_0.date()) + ' and ' + str(date_f.date()))

    entries_dates, dates = search_entries(categories, date_0, date_f, _verbose=verbose)
    for entries, date in zip(entries_dates, dates):  # Iterate over each day
        if len(entries) == 0:
            continue

        data_found = True
        print('Found ' + str(len(entries)) + ' entries for ' + str(date.date()))

        print('Formatting entries...')
        [fix_entry(entry) for entry in entries]

        print('Sorting entries...')
        entries = sort_articles(entries, keywords, authors)

        last_new_index = None
        for i in range(len(entries)):
            entries[i]['last_new'] = False
            try:
                if not entries[i]['updated_bool'] and entries[i + 1]['updated_bool']:
                    last_new_index = i
            except IndexError:
                if last_new_index is None:
                    last_new_index = i

        if last_new_index is not None:
            entries[last_new_index]['last_new'] = True

        print('Writing entries...')
        n_total = len(entries)
        with open(f'abstracts/{date.date()}.md', 'w', encoding='utf-8') as f:
            [write_article(entries[index], f, index, n_total) for index in range(n_total)]

            if args.final:
                ct = datetime.now()
                f.write(f'\n*This file was created at: {ct.strftime("%d %B %Y %H:%M:%S")}*')

    # If data not found, search one day before previous date
    date_f = date_0
    date_0 -= timedelta(days=1)

    if date_0.weekday() > 4:  # If date_0 is a weekend, search from Friday
        date_0 -= timedelta(days=date_0.weekday() - 4)

    print('')

print(f'Done with version {version} \n')

# Show closing message
n_seconds = args.time
step = 1
for i in range(0, n_seconds, step):
    print(f'Waiting {n_seconds - i} seconds before closing...', end='\r')
    sleep(step)
print('')

# Remove files from previous version
for file in os.listdir():
    if '.old' in file:
        print(f'Removing {file}')
        os.remove(file)
