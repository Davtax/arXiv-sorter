import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import List, Tuple

import feedparser
import grequests  # noqa: F401  #  imported for gevent monkey-patching side effect
import pytz

from app.__meta__ import __version__
from app.dates_functions import daterange, obtain_date, current_time_zone

BASE_URL = 'https://export.arxiv.org/api/query?'

N_MAX = 1000  # Maximum number of entries per request
T_SLEEP = 3  # seconds between requests
T_PREVIOUS_REQUEST = 0  # UTC seconds from the previous request

# ARXIV_SESSION = requests.Session()
ARXIV_OPENER = urllib.request.build_opener()
ARXIV_HEADERS = {"User-Agent": f"arxiv-sorter/{__version__}", "Accept": "application/atom+xml", }
N_RETRIES = 3


def search_entries(categories: List[str], date_0: datetime, date_f: datetime, _verbose: bool = False, ) -> Tuple[
    List[List[feedparser.FeedParserDict]], List[datetime]]:
    """
    Ask the arXiv API for the entries in the given categories and dates.
    The entries are sorted by date, with each element of the list
    containing the entries of a given day.
    """
    global T_PREVIOUS_REQUEST

    # The arXiv deadline is at 14:00 ET
    et = current_time_zone()
    deadline = datetime.now(tz=et).replace(hour=14, minute=0, second=0, microsecond=0)
    deadline_utc = deadline.astimezone(tz=pytz.utc)

    date_0 = date_0.replace(hour=deadline_utc.hour, minute=0, second=0, microsecond=0)
    date_f = date_f.replace(hour=deadline_utc.hour, minute=0, second=0, microsecond=0)

    # Dates
    date_0_str = f"{date_0.year:04d}{date_0.month:02d}{date_0.day:02d}{date_0.hour:02d}{date_0.minute:02d}"
    date_f_str = f"{date_f.year:04d}{date_f.month:02d}{date_f.day:02d}{date_f.hour:02d}{date_f.minute:02d}"

    # Search by updated date, not published date
    query = f"search_query=lastUpdatedDate:[{date_0_str}+TO+{date_f_str}]"

    # Categories
    search_query = "cat:("

    for i in range(len(categories)):
        search_query += categories[i] + "*"

        if i < len(categories) - 1:
            search_query += "+OR+"

    search_query += ")"

    if categories:
        query += f"+AND+{search_query}"

    total_entries = []

    while True:
        n_entries = f"&start={len(total_entries)}&max_results={N_MAX}"
        sort = "&sortBy=lastUpdatedDate&sortOrder=ascending"

        url = BASE_URL + query + n_entries + sort

        response = _get_arxiv_feed(url)
        entries = response.entries

        # if _verbose:
        #     print(f"The response feed is: {response_feed.feed}\n")

        total_entries += entries

        if len(entries) < N_MAX:
            break

    return _sort_entries(total_entries, date_0, date_f)


def _get_arxiv_feed(url: str) -> feedparser.FeedParserDict:
    global T_PREVIOUS_REQUEST

    for attempt in range(N_RETRIES + 1):
        elapsed_time = time.time() - T_PREVIOUS_REQUEST

        if elapsed_time < T_SLEEP:
            time.sleep(T_SLEEP - elapsed_time)

        request = urllib.request.Request(url, headers=ARXIV_HEADERS)

        try:
            with ARXIV_OPENER.open(request, timeout=30) as response:
                content = response.read()

            T_PREVIOUS_REQUEST = time.time()
            return feedparser.parse(content)

        except urllib.error.HTTPError as error:
            T_PREVIOUS_REQUEST = time.time()

            if attempt == N_RETRIES:
                raise RuntimeError(f"arXiv request failed with status code {error.code}") from error


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
