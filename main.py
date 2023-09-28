from dates_functions import check_last_date, daterange
from arXiv_api import search_entries
from read_files import read_user_file
from format_entries import fix_entry, write_article
from sort_entries import sort_articles

import os
from datetime import date, timedelta
from datetime import datetime
from time import sleep

keywords = read_user_file('keywords.txt')
authors = read_user_file('authors.txt')
categories = read_user_file('categories.txt')

if not os.path.exists('abstracts'):
    os.mkdir('abstracts')

data_0 = check_last_date() + timedelta(days=1)
data_f = date.today()

data_found = False
while not data_found:
    for single_date in daterange(data_0, data_f):
        print('Parsing arXiv API feed between ' + str(single_date) + ' and ' + str(
            single_date + timedelta(days=1)) + '...')
        entries = search_entries(categories, single_date, single_date + timedelta(days=1))

        if len(entries) > 0:
            data_found = True

            print('Formatting entries...')
            [fix_entry(entry) for entry in entries]

            print('Sorting entries...')
            entries = sort_articles(entries, keywords, authors)

            print('Writing entries...')
            n_total = len(entries)
            with open(f'abstracts/{single_date}.md', 'w', encoding='utf-8') as f:
                [write_article(entries[index], f, index, n_total) for index in range(n_total)]

                ct = datetime.now()
                f.write(f'\n*This file was created at: {ct.strftime("%d %B %Y %H:%M:%S")}*')
        else:
            sleep(t_sleep)

        print('\n')

    data_f = data_0
    data_0 -= timedelta(days=1)
