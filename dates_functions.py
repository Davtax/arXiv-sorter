from datetime import timedelta, datetime
import os


def daterange(start_date: datetime, end_date: datetime):
    """
    Generator of dates between start_date and end_date.
    """
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def check_last_date() -> datetime:
    """
    Check the last date of the file in the abstracts folder by its name.
    """
    if os.path.exists('abstracts'):
        files = os.listdir('abstracts')
        files = [file for file in files if file.find('.md') != -1]  # Remove non-markdown files

        if len(files) == 0:
            last_date = datetime.now() - timedelta(days=2)  # The search is done one day after the last date
        else:
            last_file = files[-1][:-3]
            last_date_str = last_file.split('-')  # Split in year, month and day
            last_date = datetime(int(last_date_str[0]), int(last_date_str[1]), int(last_date_str[2]))

    else:
        last_date = datetime.now() - timedelta(days=2)

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
