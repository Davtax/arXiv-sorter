from datetime import date, timedelta, datetime
import os


def daterange(start_date: date, end_date: date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def check_last_date() -> date:
    if os.path.exists('abstracts'):
        files = os.listdir('abstracts')
        files = [file for file in files if file.find('.md') != -1]

        if len(files) == 0:
            last_date = date.today() - timedelta(days=2)
        else:
            last_file = files[-1][:-3]
            last_date_str = last_file.split('-')
            last_date = date(int(last_date_str[0]), int(last_date_str[1]), int(last_date_str[2]))

    else:
        last_date = date.today() - timedelta(days=2)

    return last_date


def obtain_data(data: str) -> datetime:
    data = data.split('T')
    date = data[0].split('-')
    time = data[1].split(':')

    date = datetime(int(date[0]), int(date[1]), int(date[2]), int(time[0]), int(time[1]), int(time[2][:2]))

    return date
