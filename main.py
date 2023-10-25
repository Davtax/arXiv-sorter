import os
from datetime import timedelta, datetime

from dates_functions import check_last_date
from arXiv_api import search_entries
from read_files import read_user_file
from format_entries import fix_entry, write_article
from sort_entries import sort_articles

# path = '/Users/david/Library/CloudStorage/OneDrive-UAM/arXiv-sorter/'
# os.chdir(path)

version = '0.0.5'

keywords = read_user_file('keywords.txt')
authors = read_user_file('authors.txt', sort=True)
categories = read_user_file('categories.txt', sort=True)

if not os.path.exists('abstracts'):
    os.mkdir('abstracts')

date_0 = check_last_date() + timedelta(days=1)
date_f = datetime.now()

data_found = False
while not data_found:
    print('Requesting arXiv API feed between ' + str(date_0.date()) + ' and ' + str(date_f.date()) + '\n')
    entries_dates, dates = search_entries(categories, date_0, date_f)
    for entries, date in zip(entries_dates, dates):
        if len(entries) == 0:
            continue

        data_found = True
        print('Found ' + str(len(entries)) + ' entries for ' + str(date.date()))

        print('Formatting entries...')
        [fix_entry(entry) for entry in entries]

        print('Sorting entries...')
        entries = sort_articles(entries, keywords, authors)

        print('Writing entries...\n')
        n_total = len(entries)
        with open(f'abstracts/{date.date()}.md', 'w', encoding='utf-8') as f:
            [write_article(entries[index], f, index, n_total) for index in range(n_total)]

            ct = datetime.now()
            f.write(f'\n*This file was created at: {ct.strftime("%d %B %Y %H:%M:%S")}*')

    date_f = date_0
    date_0 -= timedelta(days=1)

print(f'Done with version {version}')
input('Press ENTER to exit')
