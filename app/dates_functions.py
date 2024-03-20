import os
from datetime import datetime, timedelta

import pytz


def daterange(start_date: datetime, end_date: datetime):
    """
    Generator of dates between start_date and end_date.
    """
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def check_last_date(folder_name: str, separate_files: bool) -> datetime:
    """
    Check the last date of the file in the abstracts folder by its name.
    """
    if os.path.exists(folder_name):
        files = os.listdir(folder_name)
        if separate_files:
            files = [file for file in files if file.find('.md') == -1]
        else:
            files = [file for file in files if file.find('.md') != -1]  # Remove non-markdown files
        files = sorted(files)  # Sort files by name

        if len(files) == 0:
            last_date = None
        else:
            last_file = files[-1].split('.')[0]
            last_date_str = last_file.split('-')  # Split in year, month and day
            last_date = datetime(int(last_date_str[0]), int(last_date_str[1]), int(last_date_str[2]))

    else:
        last_date = datetime.now()

    return last_date


def obtain_date(date: str) -> datetime:
    """
    Obtain datetime object from date string in the format: YYYY-MM-DDTHH:MM:SSZ
    """
    date = date.split('T')
    date_str = date[0].split('-')  # Split in year, month and day
    time = date[1].split(':')  # Split in hour, minute and second

    date_str = datetime(int(date_str[0]), int(date_str[1]), int(date_str[2]), int(time[0]), int(time[1]),
                        int(time[2][:2]))

    return date_str


def current_time_zone():
    et = pytz.timezone('US/Eastern')
    utc = pytz.utc
    return datetime.now(tz=utc).astimezone(et).tzinfo


def current_utc_timestamp() -> float:
    return datetime.utcnow().timestamp()


def prev_mail(date: datetime) -> datetime:
    """
    Get the previous mail date.
    """
    date -= timedelta(days=1)
    if date.weekday() > 4:  # If date is a weekend, search from Friday
        date -= timedelta(days=date.weekday() - 4)

    return date


def next_mail(date: datetime) -> datetime:
    """
    Get the next mail date.
    """
    date += timedelta(days=1)
    if date.weekday() > 4:  # If date_0 is a weekend, search from Monday
        date += timedelta(days=7 - date.weekday())

    return date
