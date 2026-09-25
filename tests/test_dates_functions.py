import time
from datetime import datetime, timedelta

import pytest

from app.dates_functions import (
    check_last_date,
    current_utc_timestamp,
    daterange,
    next_mail,
    obtain_date,
    prev_mail,
)

# 2026-09-21 is a Monday
MON, TUE, THU, FRI, SAT, SUN = (datetime(2026, 9, d) for d in (21, 22, 24, 25, 26, 27))


def test_daterange_excludes_end_date():
    assert list(daterange(MON, THU)) == [MON, TUE, datetime(2026, 9, 23)]


def test_daterange_is_empty_for_non_positive_ranges():
    assert list(daterange(MON, MON)) == []
    assert list(daterange(THU, MON)) == []


def test_obtain_date_parses_arxiv_timestamps():
    assert obtain_date('2026-09-24T17:59:03Z') == datetime(2026, 9, 24, 17, 59, 3)


@pytest.mark.parametrize(
    ('date', 'expected'),
    [(TUE, MON), (MON, datetime(2026, 9, 18)), (SAT, FRI), (SUN, FRI)],
    ids=['tuesday', 'monday', 'saturday', 'sunday'],
)
def test_prev_mail_skips_weekends(date, expected):
    assert prev_mail(date) == expected


@pytest.mark.parametrize(
    ('date', 'expected'),
    [(MON, TUE), (THU, FRI), (FRI, datetime(2026, 9, 28)), (SAT, datetime(2026, 9, 28))],
    ids=['monday', 'thursday', 'friday', 'saturday'],
)
def test_next_mail_skips_weekends(date, expected):
    assert next_mail(date) == expected


def test_current_utc_timestamp_is_the_unix_epoch():
    assert current_utc_timestamp() == pytest.approx(time.time(), abs=5)


class TestCheckLastDate:
    def test_missing_folder_defaults_to_now(self, tmp_path):
        last = check_last_date(tmp_path / 'missing', separate_files=False)
        assert datetime.now() - last < timedelta(seconds=5)

    def test_empty_folder_returns_none(self, tmp_path):
        assert check_last_date(tmp_path, separate_files=False) is None

    def test_ignores_files_that_are_not_dates(self, tmp_path):
        (tmp_path / '2026-01-02.md').touch()
        (tmp_path / '2026-05-05.txt').touch()
        (tmp_path / 'notes.md').touch()
        assert check_last_date(tmp_path, separate_files=False) == datetime(2026, 1, 2)

    def test_uses_matching_files_or_directories_only(self, tmp_path):
        (tmp_path / '2026-01-02.md').touch()
        (tmp_path / 'figures').mkdir()
        (tmp_path / '2026-01-03').mkdir()

        assert check_last_date(tmp_path, separate_files=False) == datetime(2026, 1, 2)
        assert check_last_date(tmp_path, separate_files=True) == datetime(2026, 1, 3)
