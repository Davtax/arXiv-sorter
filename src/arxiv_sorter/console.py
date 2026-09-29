"""
Interaction with the user through the terminal (or through the GUI, which runs the program in a separate process).

Messages are printed with `step`, `info`, `success`, `warning`, `error` and `detail` (only shown with --verbose). In a
terminal they get an icon and a color when the terminal supports them; in the GUI they are sent as tagged lines, and
the window shows them with its own style.
"""
import io
import os
import sys
from dataclasses import dataclass
from os import get_terminal_size
from pathlib import Path
from time import sleep, time
from typing import TextIO

from arxiv_sorter.protocol import LOG_TAG, PROGRESS_TAG, QUESTION_TAG, WRITTEN_TAG, Level, gui_mode

# When run from the GUI, messages, progress bars and questions are sent to it as tagged lines (see protocol.py)
GUI_MODE = gui_mode()

PLAIN_ENV_VAR = 'ARXIV_SORTER_PLAIN'  # Set to 1 to print without icons nor colors

ICONS = {Level.SUCCESS: '✅', Level.WARNING: '⚠️', Level.ERROR: '❌'}  # Default icon of each level
ANSI = {Level.STEP: '\033[1;36m', Level.SUCCESS: '\033[32m', Level.WARNING: '\033[33m', Level.ERROR: '\033[1;31m',
        Level.DETAIL: '\033[2m'}
ANSI_RESET = '\033[0m'


@dataclass
class Style:
    """
    What the terminal can show.
    """
    icons: bool = True
    colors: bool = False


STYLE = Style()
VERBOSE = False


def set_verbose(verbose: bool):
    global VERBOSE
    VERBOSE = verbose


def _enable_windows_colors() -> bool:
    """
    Enable the ANSI escape codes in the Windows console (on by default in Windows Terminal, but not in the old console).
    """
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # Standard output
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except (AttributeError, OSError):
        return False


def detect_style(stream: TextIO, environment: dict[str, str], platform: str) -> Style:
    """
    Icons and colors supported by the terminal: colors only in interactive terminals (following the NO_COLOR
    convention), and icons everywhere except in the old Windows console, which shows emojis as empty boxes.
    """
    if environment.get(PLAIN_ENV_VAR) == '1':
        return Style(icons=False, colors=False)

    interactive = hasattr(stream, 'isatty') and stream.isatty()
    modern_windows_terminal = any(name in environment for name in ('WT_SESSION', 'TERM_PROGRAM', 'ConEmuANSI'))
    icons = not (platform == 'win32' and interactive and not modern_windows_terminal)
    colors = interactive and 'NO_COLOR' not in environment and environment.get('TERM') != 'dumb'
    return Style(icons=icons, colors=colors)


def configure_stdout():
    """
    Use UTF-8 (the Windows console may use a legacy code page), and flush every line so the messages are shown right
    away, also when the output is redirected (e.g. to the GUI or to a log file). Then detect the style of the terminal.
    """
    global STYLE
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

    STYLE = detect_style(sys.stdout, dict(os.environ), sys.platform)
    if STYLE.colors and sys.platform == 'win32':
        STYLE.colors = _enable_windows_colors()


def message(level: Level, text: str, icon: str = ''):
    """
    Print a message. `icon` (an emoji) replaces the default icon of the level.
    """
    if level is Level.DETAIL and not VERBOSE:
        return

    icon = icon or ICONS.get(level, '')
    for line in str(text).splitlines() or ['']:
        if GUI_MODE:
            print(f'{LOG_TAG}{level}\t{icon}\t{line}', flush=True)
            continue

        if level is Level.STEP:
            print()  # Headings are separated from the previous stage
        prefix = f'{icon} ' if icon and STYLE.icons else ''
        indent = '   ' if level is Level.DETAIL else ''
        text_line = f'{indent}{prefix}{line}'
        if STYLE.colors and level in ANSI:
            text_line = f'{ANSI[level]}{text_line}{ANSI_RESET}'
        print(text_line, flush=True)
        icon = ''  # Only on the first line of multi-line messages


def step(text: str, icon: str = ''):
    message(Level.STEP, text, icon)


def info(text: str, icon: str = ''):
    message(Level.INFO, text, icon)


def success(text: str, icon: str = ''):
    message(Level.SUCCESS, text, icon)


def warning(text: str, icon: str = ''):
    message(Level.WARNING, text, icon)


def error(text: str, icon: str = ''):
    message(Level.ERROR, text, icon)


def detail(text: str, icon: str = ''):
    message(Level.DETAIL, text, icon)


def timing_message(total_time: int, message_text: str, step_time: int = 1):
    icon = '⏳ ' if STYLE.icons and not GUI_MODE else ''
    for i in range(0, total_time, step_time):
        print(f'{icon}Waiting {total_time - i} s {message_text}', end='\r', flush=True)
        sleep(step_time)
    print('')


def report_written(path: Path, n_entries: int, n_new: int):
    """
    Tell the GUI that the entries of a mailing list were written (a Markdown file, or a folder with --separate), so it
    can list them at the end. Format: tag, number of entries, number of new ones and path separated by tabs.
    """
    if GUI_MODE:
        print(f'{WRITTEN_TAG}{n_entries}\t{n_new}\t{path.resolve()}', flush=True)


def question(text: str) -> bool:
    """
    Ask a yes/no question (in a dialog in the GUI). An empty answer means yes, and the question is repeated until the
    answer is understood.
    """
    if GUI_MODE:  # The GUI shows the question in a dialog, and writes the answer to the standard input
        print(QUESTION_TAG + text, flush=True)
        answer = input().lower()
    else:
        icon = '❓ ' if STYLE.icons else ''
        answer = input(f'{icon}{text} [Y/n]: ').strip().lower()

    if answer in ('y', 'yes', ''):
        return True
    if answer in ('n', 'no'):
        return False

    warning("Sorry, I didn't understand the answer. Please write y (yes) or n (no).")
    return question(text)


def _format_time(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f'{minutes:02}:{seconds:02}'


class Progressbar:
    """
    Progress bar in the terminal (or in the GUI), e.g. `📥 Downloading PDFs  ██████░░░░  12/40  00:05 < 00:12`.
    """

    def __init__(self, count: int, prefix: str = "", size: int = 30, out: TextIO | None = None, icon: str = ''):
        self.count = count
        self.current = 0
        self.start = time()

        self.size = size
        self.prefix = prefix
        self.icon = icon
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

        elapsed = time() - self.start
        remaining = elapsed / self.current * (self.count - self.current)

        icon = f'{self.icon} ' if self.icon and STYLE.icons else ''
        pre = f'{icon}{self.prefix}  '
        pos = f'  {self.current}/{self.count}  {_format_time(elapsed)} < {_format_time(remaining)}'

        size = self.size
        if self.terminal_size is not None:
            size = max(min(self.terminal_size.columns - len(pre) - len(pos) - 3, self.size), 0)
            print(' ' * (self.terminal_size.columns - 1), end='\r', flush=True, file=self.out)
        else:
            print('\r', end='', file=self.out)

        filled = int(size * self.current / self.count)
        print(f"{pre}{'█' * filled}{'░' * (size - filled)}{pos}", end='\r', flush=True, file=self.out)

    def close(self):
        if GUI_MODE:
            return
        print('', flush=True, file=self.out)
