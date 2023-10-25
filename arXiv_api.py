import feedparser
import time
from typing import List, Tuple
from datetime import datetime, timedelta

from dates_functions import daterange, obtain_date

base_url = 'https://export.arxiv.org/api/query?'

n_max = 1000
t_sleep = 3  # seconds
t_previous_request = 0


def search_entries(categories: List[str], date_0: datetime, date_f: datetime) -> Tuple[
    List[List[feedparser.FeedParserDict]], List[datetime]]:
    global t_previous_request

    date_0 = date_0.replace(hour=18, minute=0, second=0, microsecond=0)
    date_f = date_f.replace(hour=18, minute=0, second=0, microsecond=0)

    # Categories
    search_query = 'cat:('

    for i in range(len(categories)):
        search_query += categories[i] + '*'
        if i < len(categories) - 1:
            search_query += '+OR+'
    search_query += ')'

    # Dates
    date_0_str = f'{date_0.year:04d}{date_0.month:02d}{date_0.day:02d}{date_0.hour:02d}{date_0.minute:02d}'
    date_f_str = f'{date_f.year:04d}{date_f.month:02d}{date_f.day:02d}{date_f.hour:02d}{date_f.minute:02d}'

    query = f'search_query=lastUpdatedDate:[{date_0_str}+TO+{date_f_str}]'

    if len(categories) != 0:
        query += f'+AND+{search_query}'

    # Search
    total_entries = []
    counter = 0
    while True:
        n_entries = f'&start={counter}&max_results={n_max}'
        sort = '&sortBy=lastUpdatedDate&sortOrder=ascending'

        elapsed_time = time.time() - t_previous_request
        if elapsed_time < t_sleep:
            time.sleep(t_sleep - elapsed_time)

        t_previous_request = time.time()
        entries = feedparser.parse(base_url + query + n_entries + sort).entries

        total_entries += entries
        if len(entries) == 0 or len(entries) < n_max:
            break
        else:
            counter += n_max

    return _sort_entries(total_entries, date_0, date_f)


def _sort_entries(entries: List[feedparser.FeedParserDict], date_0: datetime, date_f: datetime) -> Tuple[
    List[List[feedparser.FeedParserDict]], List[datetime]]:
    total_entries_date = []
    dates = []

    counter = 0
    for j, single_date in enumerate(daterange(date_0, date_f)):

        if single_date.weekday() < 4:  # Monday, Tuesday, Wednesday and Thursday
            shift = timedelta(days=1)
        elif single_date.weekday() == 4:  # Friday
            shift = timedelta(days=3)
        else:  # Saturday and Sunday
            continue

        total_entries_date.append([])
        for i in range(counter, len(entries)):
            if single_date <= obtain_date(entries[i].updated) < single_date + shift:
                total_entries_date[-1].append(entries[i])
            else:
                counter = i
                break
        dates.append(single_date)

    return total_entries_date, dates
