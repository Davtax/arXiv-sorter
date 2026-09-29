"""
Interaction with the user through the terminal (or through the GUI, which runs the program in a separate process).
"""
import io
import sys
from os import get_terminal_size
from pathlib import Path
from time import sleep, time
from typing import TextIO

from arxiv_sorter.protocol import PROGRESS_TAG, QUESTION_TAG, WRITTEN_TAG, gui_mode

# When run from the GUI, progress bars and questions are sent to it as tagged lines through the standard output
GUI_MODE = gui_mode()


def configure_stdout():
    """
    Use UTF-8 (the Windows console may use a legacy code page), and flush every line so the messages are shown right
    away, also when the output is redirected (e.g. to the GUI or to a log file).
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)


def timing_message(total_time: int, message: str, step: int = 1):
    for i in range(0, total_time, step):
        print(f'Waiting {total_time - i} seconds {message}', end='\r', flush=True)
        sleep(step)
    print('')


def report_written(path: Path, n_entries: int, n_new: int):
    """
    Tell the GUI that the entries of a mailing list were written (a Markdown file, or a folder with --separate), so it
    can list them at the end. Format: tag, number of entries, number of new ones and path separated by tabs.
    """
    if GUI_MODE:
        print(f'{WRITTEN_TAG}{n_entries}\t{n_new}\t{path.resolve()}', flush=True)


def question(message: str) -> bool:
    """
    Make a question and return True or False depending on the answer of the user. There is only two possible answers
    y -> yes or	n -> no. If the answer is none of this two the question is repeated until a good answer is given.
    If not message is provided, then the default overwriting file message is printed, with the file name provided.
    """
    if GUI_MODE:  # The GUI shows the question in a dialog, and writes the answer to the standard input
        print(QUESTION_TAG + message, flush=True)
        temp = input().lower()
    else:
        temp = input(message + ' [y]/n: ').lower()  # Ask for an answer by keyword input

    if temp == 'y' or temp == '':
        return True
    elif temp == 'n':
        return False
    else:  # If the answer is not correct
        print('I didn\'t understand your answer.')
        return question(message)  # The function will repeat until a correct answer if provided


class Progressbar:
    def __init__(self, count: int, prefix: str = "", size: int = 40, out: TextIO | None = None):
        self.count = count
        self.current = 0
        self.start = time()

        self.size = size
        self.prefix = prefix
        self.out = out if out is not None else sys.stdout

        try:
            self.terminal_size = get_terminal_size()
        except OSError:
            self.terminal_size = None

    def update(self, j: int = 1):
        self.current += j

        if GUI_MODE:  # Format: tag, current, count and prefix separated by tabs
            print(f'{PROGRESS_TAG}{self.current}\t{self.count}\t{self.prefix}', flush=True, file=self.out)
            return

        remaining = ((time() - self.start) / self.current) * (self.count - self.current)

        try:
            rate = self.current / (time() - self.start)
        except ZeroDivisionError:
            rate = 0

        mins, sec = divmod(remaining, 60)
        time_str = f"{int(mins):02}:{int(sec):02}"

        current_time = time() - self.start
        mins_current, sec_current = divmod(current_time, 60)
        time_str_current = f"{int(mins_current):02}:{int(sec_current):02}"

        pre = f'{self.prefix}'
        pos = f'{self.current}/{self.count}[{time_str_current}<{time_str}, {rate:.2f} it/s]'

        if self.terminal_size is None:
            size = self.size
            print('\r', end='')
        else:
            text_size = len(pre) + len(pos) + 3
            size = max(self.terminal_size.columns - text_size, 0)
            size = min(size, self.size)
            print(' ' * self.terminal_size.columns, end='\r', flush=True, file=self.out)

        x = int(size * self.current / self.count)
        msg = f"{pre}[{'█' * x}{('.' * (size - x))}] {pos}"

        print(msg, end='\r', flush=True, file=self.out)

    def close(self):
        if GUI_MODE:
            return
        # print('\n', flush=True, file=self.out)
        print('', flush=True, file=self.out)
