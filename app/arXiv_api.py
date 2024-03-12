import time
from datetime import datetime, timedelta
from typing import List, Tuple
import pytz

import feedparser
# import grequests
import requests

from app.dates_functions import daterange, obtain_date, current_time_zone

base_url = 'https://export.arxiv.org/api/query?'

n_max = 1000  # Maximum number of entries per request
t_sleep = 3  # seconds between requests
t_previous_request = 0  # UTC seconds from the previous request


def search_entries(categories: List[str], date_0: datetime, date_f: datetime, _verbose: bool = False) -> Tuple[
    List[List[feedparser.FeedParserDict]], List[datetime]]:
    """
    Ask the arXiv API for the entries in the given categories and dates. The entries are sorted by date, with each
    element of the list containing the entries of a given day.
    """
    global t_previous_request

    #  The arXiv deadline is at 14:00 ET
    et = current_time_zone()
    deadline = datetime.now(tz=et).replace(hour=14, minute=0, second=0, microsecond=0)
    deadline_utc = deadline.astimezone(tz=pytz.utc)

    date_0 = date_0.replace(hour=deadline_utc.hour, minute=0, second=0, microsecond=0)
    date_f = date_f.replace(hour=deadline_utc.hour, minute=0, second=0, microsecond=0)

    # Dates
    date_0_str = f'{date_0.year:04d}{date_0.month:02d}{date_0.day:02d}{date_0.hour:02d}{date_0.minute:02d}'
    date_f_str = f'{date_f.year:04d}{date_f.month:02d}{date_f.day:02d}{date_f.hour:02d}{date_f.minute:02d}'

    # Search by updated date, not published date
    query = f'search_query=lastUpdatedDate:[{date_0_str}+TO+{date_f_str}]'

    # Categories
    search_query = 'cat:('

    for i in range(len(categories)):
        search_query += categories[i] + '*'  # Search in all subcategories
        if i < len(categories) - 1:
            search_query += '+OR+'
    search_query += ')'

    if len(categories) != 0:  # If there are no categories, the search query is only by date
        query += f'+AND+{search_query}'

    # Keep asking for entries until there are no more entries in the range of dates
    total_entries = []
    while True:
        n_entries = f'&start={len(total_entries)}&max_results={n_max}'
        sort = '&sortBy=lastUpdatedDate&sortOrder=ascending'

        elapsed_time = time.time() - t_previous_request  # Wait at least t_sleep seconds between requests
        if elapsed_time < t_sleep:
            time.sleep(t_sleep - elapsed_time)

        t_previous_request = time.time()

        # Do not know why, but it is necessary for Mac to use requests, and then feedparser
        response = requests.get(base_url + query + n_entries + sort)
        response = feedparser.parse(response.text)  # Ask for entries
        entries = response.entries  # Get entries

        if _verbose:
            print(f'The response feed is: {response.feed} \n')

        total_entries += entries
        if len(entries) == 0 or len(entries) < n_max:  # If there are no more entries, stop
            break

    return _sort_entries(total_entries, date_0, date_f)


def _sort_entries(entries: List[feedparser.FeedParserDict], date_0: datetime, date_f: datetime) -> Tuple[
    List[List[feedparser.FeedParserDict]], List[datetime]]:
    total_entries_date = []
    dates = []

    entries = sorted(entries, key=lambda x: x.updated)  # Sort entries by date (sometimes arXiv does not sort them)

    counter = 0  # Counter to keep track of the entries already sorted
    for j, single_date in enumerate(daterange(date_0, date_f)):

        # Entries from weekdays are separated, and entries from weekends are grouped together
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
                counter += 1
            else:
                break
        dates.append(single_date)

    if counter < len(entries):
        print('There are entries that were not sorted. Appending them to the last date.')
        total_entries_date[-1] += entries[counter:]

    return total_entries_date, dates
