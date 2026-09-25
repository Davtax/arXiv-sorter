import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from subprocess import TimeoutExpired, run

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
TIMEOUT = 30  # seconds


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


def _wait_between_requests():
    """
    arXiv asks for no more than one request every 3 seconds.
    """
    global T_PREVIOUS_REQUEST

    elapsed_time = time.time() - T_PREVIOUS_REQUEST
    if elapsed_time < T_SLEEP:
        time.sleep(T_SLEEP - elapsed_time)
    T_PREVIOUS_REQUEST = time.time()


def _fetch_urllib(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=ARXIV_HEADERS)
    try:
        with ARXIV_OPENER.open(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _fetch_curl(url: str) -> tuple[int, bytes] | None:
    """
    Same request through the curl of the system (shipped with Windows 10+, macOS and most Linux distributions).
    Returns None if curl is not available.
    """
    # --globoff: the date range of the query uses [], which curl interprets as a pattern otherwise
    args = ['curl', '--silent', '--show-error', '--globoff', '--max-time', str(TIMEOUT),
            '--write-out', '\n%{http_code}']
    for key, value in ARXIV_HEADERS.items():
        args += ['--header', f'{key}: {value}']

    try:
        result = run(args + [url], capture_output=True, timeout=TIMEOUT + 5)
    except (FileNotFoundError, TimeoutExpired):
        return None

    content, _, status = result.stdout.rpartition(b'\n')
    if result.returncode != 0 or not status.isdigit():
        return None
    return int(status), content


def _parse_feed(content: bytes) -> feedparser.FeedParserDict | None:
    """
    Parse the Atom feed, returning None if the content is not a valid arXiv feed (e.g. empty body).
    """
    feed = feedparser.parse(content)
    if feed.bozo or 'id' not in feed.feed:
        return None
    return feed


def _get_arxiv_feed(url: str) -> feedparser.FeedParserDict:
    """
    Request the url to the arXiv API, respecting the minimum time between requests, and retrying on errors.

    Since September 2026, arXiv's CDN throttles some HTTP clients by answering 406 (usually with an empty body) to
    requests that miss its cache, while accepting the same request from other clients. On a 406 the request is
    repeated through curl, and in any case retried with an exponential backoff.
    """
    status = None
    for attempt in range(N_RETRIES + 1):
        if attempt > 0:
            wait = T_SLEEP * 2 ** attempt
            print(f'arXiv API answered with status code {status}, retrying in {wait} seconds ...')
            time.sleep(wait)

        _wait_between_requests()
        try:
            status, content = _fetch_urllib(url)
        except urllib.error.URLError as error:  # No connection, timeout, ...
            status, content = str(error.reason), b''

        # Sometimes arXiv answers 406 with a valid feed in the body
        if status == 200 or status == 406:
            feed = _parse_feed(content)
            if feed is not None:
                return feed

        if status == 406:
            _wait_between_requests()
            curl_response = _fetch_curl(url)
            if curl_response is not None:
                status, content = curl_response
                feed = _parse_feed(content) if status in (200, 406) else None
                if feed is not None:
                    return feed

    raise RuntimeError(f"arXiv request failed with status code {status}")


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
