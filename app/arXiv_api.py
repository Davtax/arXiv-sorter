import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import feedparser
import grequests  # noqa: F401  #  imported for gevent monkey-patching side effect
import pytz

from app.__meta__ import __version__
from app.dates_functions import current_time_zone, daterange, obtain_date

BASE_URL = 'https://export.arxiv.org/api/query?'

N_MAX = 1000  # Maximum number of entries per request
T_SLEEP = 3  # seconds between requests
T_PREVIOUS_REQUEST = 0  # UTC seconds from the previous request

ARXIV_OPENER = urllib.request.build_opener()
ARXIV_HEADERS = {"User-Agent": f"arxiv-sorter/{__version__}", "Accept": "application/atom+xml", }
N_RETRIES = 3


def search_entries(categories: list[str], date_0: datetime, date_f: datetime, _verbose: bool = False, ) -> tuple[
    list[list[feedparser.FeedParserDict]], list[datetime]]:
    """
    Ask the arXiv API for the entries in the given categories and dates.
    The entries are sorted by date, with each element of the list
    containing the entries of a given day.
    """
    # The arXiv deadline is at 14:00 ET
    et = current_time_zone()
    deadline = datetime.now(tz=et).replace(hour=14, minute=0, second=0, microsecond=0)
    deadline_utc = deadline.astimezone(tz=pytz.utc)

    date_0 = date_0.replace(hour=deadline_utc.hour, minute=0, second=0, microsecond=0)
    date_f = date_f.replace(hour=deadline_utc.hour, minute=0, second=0, microsecond=0)

    # Search by updated date, not published date
    query = f"search_query=lastUpdatedDate:[{date_0:%Y%m%d%H%M}+TO+{date_f:%Y%m%d%H%M}]"

    if categories:
        query += "+AND+cat:(" + "+OR+".join(f"{category}*" for category in categories) + ")"

    total_entries = []

    while True:
        n_entries = f"&start={len(total_entries)}&max_results={N_MAX}"
        sort = "&sortBy=lastUpdatedDate&sortOrder=ascending"

        entries = _get_arxiv_feed(BASE_URL + query + n_entries + sort).entries
        total_entries += entries

        if len(entries) < N_MAX:
            break

    return _sort_entries(total_entries, date_0, date_f)


def _get_arxiv_feed(url: str) -> feedparser.FeedParserDict:
    """
    Request the url to the arXiv API, respecting the minimum time between requests, and retrying on HTTP errors.
    """
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


def _sort_entries(entries: list[feedparser.FeedParserDict], date_0: datetime, date_f: datetime) -> tuple[
    list[list[feedparser.FeedParserDict]], list[datetime]]:
    """
    Group the entries by mailing date. Entries from weekdays are separated, and the ones from Friday to Monday (before
    the deadline) are grouped together in the Friday mail.
    """
    total_entries_date = []
    dates = []

    entries = sorted(entries, key=lambda x: x.updated)  # Sort entries by date (sometimes arXiv does not sort them)

    counter = 0  # Counter to keep track of the entries already sorted
    for single_date in daterange(date_0, date_f):
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
