import feedparser
import time
from typing import List
from datetime import date

base_url = 'https://export.arxiv.org/api/query?'

n_max = 100
t_sleep = 3  # seconds


def search_entries(categories: List[str], date_0: date, date_f: date) -> List[feedparser.FeedParserDict]:
    # Categories
    search_query = 'cat:('

    for i in range(len(categories)):
        search_query += categories[i] + '*'
        if i < len(categories) - 1:
            search_query += '+OR+'
    search_query += ')'

    # Dates
    date_0 = f'{date_0.year:04d}{date_0.month:02d}{date_0.day:02d}1800'
    date_f = f'{date_f.year:04d}{date_f.month:02d}{date_f.day:02d}1800'
    query = f'search_query={search_query}+AND+lastUpdatedDate:[{date_0}+TO+{date_f}]'

    # Search
    total_entries = []
    counter = 0
    while True:
        n_entries = f'&start={counter}&max_results={n_max}'
        sort = '&sortBy=lastUpdatedDate&sortOrder=ascending'

        entries = feedparser.parse(base_url + query + n_entries + sort).entries

        total_entries += entries
        if len(entries) == 0 or len(entries) < n_max:
            break
        else:
            counter += n_max
            time.sleep(t_sleep)

    return total_entries
