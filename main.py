from dates_functions import check_last_date, daterange
from arXiv_api import search_entries
from read_files import read_user_file
from format_entries import fix_entry, sort_articles, write_article

import os
from datetime import date, timedelta
from datetime import datetime

keywords = read_user_file('keywords.txt')
authors = read_user_file('authors.txt')
categories = read_user_file('categories.txt')

if not os.path.exists('abstracts'):
    os.mkdir('abstracts')

if len(os.listdir('abstracts')) == 0:
    previous_data = False
else:
    previous_data = True

data_0 = check_last_date() + timedelta(days=1)
data_f = date.today()

data_found = False
while not data_found:
    for single_date in daterange(data_0, data_f):
        print('Parsing arXiv API feed between ' + str(single_date) + ' and ' + str(single_date + timedelta(days=1)) + '...')
        entries = search_entries(categories, single_date, single_date + timedelta(days=1))

        if len(entries) > 0:
            data_found = True

        print('Formatting entries...')
        [fix_entry(entry) for entry in entries]

        print('Sorting entries...')
        entries = sort_articles(entries, keywords, authors)

        print('Writing entries...')
        n_total = len(entries)
        with open(f'abstracts/{single_date}.md', 'w') as f:
            [write_article(entries[index], f, index, n_total) for index in range(n_total)]

            ct = datetime.now()
            f.write(f'\n\n*Last updated: {ct.strftime("%d %B %Y %H:%M:%S")}*')

    if previous_data:  # If data existed before, only search between the last date and today
        break
    elif not previous_data:  # If data didn't exist before, search until the first date with data
        data_f = data_0
        data_0 -= timedelta(days=1)
