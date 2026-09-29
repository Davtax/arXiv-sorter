"""
Preview of the search terms against real submissions, used by the editor of the search files: which submissions of the
latest mailing list would match, before saving the files.
"""
import contextlib
import copy
from dataclasses import dataclass
from datetime import datetime

from feedparser import FeedParserDict

from arxiv_sorter.arxiv_api import search_entries
from arxiv_sorter.dates import prev_mail
from arxiv_sorter.formatting import fix_entry
from arxiv_sorter.search_terms import Kind, Severity, check_lines
from arxiv_sorter.sorting import sort_articles
from arxiv_sorter.user_files import normalize_lines

MAX_DAYS_BACK = 5  # Mailing lists tried, going back from today, to find one with submissions (e.g. after a weekend)


@dataclass
class LatestSubmissions:
    date: datetime
    entries: list[FeedParserDict]  # Already fixed (see formatting.fix_entry)


def fetch_latest(categories: list[str], now: datetime | None = None) -> LatestSubmissions | None:
    """
    Submissions of the latest mailing list with any, in the given categories (all if empty). None if nothing is found.
    """
    date_f = now or datetime.now()
    for _ in range(MAX_DAYS_BACK):
        date_0 = prev_mail(date_f)
        entries_dates, dates = search_entries(categories, date_0, date_f)
        for entries, date in zip(reversed(entries_dates), reversed(dates), strict=True):  # Latest first
            if entries:
                for entry in entries:
                    with contextlib.suppress(IndexError):  # Kept as it is, as in the run
                        fix_entry(entry)
                return LatestSubmissions(date, entries)
        date_f = date_0
    return None


def custom_entry(title: str, abstract: str, authors: str) -> FeedParserDict:
    """
    Entry with a text written by the user, to test the search terms on it. `authors` are separated by commas, as in
    the entries of the run.
    """
    return FeedParserDict(id='custom', title=' '.join(title.split()), summary=' '.join(abstract.split()),
                          authors=', '.join(name.strip() for name in authors.split(',') if name.strip()),
                          updated_bool=False)


def usable_terms(lines: list[str], kind: Kind) -> list[str]:
    """
    Terms as used by the sorting (normalized, without comments nor repetitions), leaving out the lines with mistakes.
    """
    wrong_lines = {problem.line for problem in check_lines(lines, kind) if problem.severity is Severity.ERROR}
    valid = [line for number, line in enumerate(lines, start=1) if number not in wrong_lines]
    terms = normalize_lines(valid)
    return [rf'\b{term}\b' for term in terms] if kind is Kind.AUTHORS else terms


def matching_entries(entries: list[FeedParserDict], keyword_lines: list[str],
                     author_lines: list[str]) -> list[FeedParserDict]:
    """
    Entries that match the keywords or the authors, with the matches highlighted (HTML), in the order of the run.
    The given entries are not modified.
    """
    keywords = usable_terms(keyword_lines, Kind.KEYWORDS)
    authors = usable_terms(author_lines, Kind.AUTHORS)
    if not keywords and not authors:
        return []

    ordered = sort_articles(copy.deepcopy(entries), keywords, authors)
    return [entry for entry in ordered if entry['index'] > 0]  # 0 and -1 are the entries without matches
