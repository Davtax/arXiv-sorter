"""
Log file of each run, kept in the configuration folder to report problems. It contains every message, also the details
only shown with --verbose and the full description of the errors.
"""
import contextlib
import logging
import platform
import sys
from datetime import datetime
from pathlib import Path

from arxorter import __version__
from arxorter.system import config_dir

LOGGER = logging.getLogger('arxorter')
LOGGER.addHandler(logging.NullHandler())  # Nothing is printed by logging itself (the console module prints)
LOGGER.propagate = False
LOGGER.setLevel(logging.DEBUG)

KEEP = 30  # Log files of the last runs that are kept
FORMAT = '%(asctime)s  %(levelname)-7s  %(message)s'


def logs_dir() -> Path:
    return config_dir() / 'logs'


def log_files() -> list[Path]:
    """
    Log files, from the oldest to the newest.
    """
    return sorted(logs_dir().glob('*.log'))


def latest_log() -> Path | None:
    files = log_files()
    return files[-1] if files else None


def start_log_file(argv: list[str]) -> Path | None:
    """
    Start the log file of this run, and delete the oldest ones. Returns None if it cannot be written (the run goes on
    without it).
    """
    for handler in [handler for handler in LOGGER.handlers if isinstance(handler, logging.FileHandler)]:
        LOGGER.removeHandler(handler)
        handler.close()

    try:
        logs_dir().mkdir(parents=True, exist_ok=True)
        path = logs_dir() / f'{datetime.now():%Y-%m-%d %H-%M-%S}.log'
        handler = logging.FileHandler(path, encoding='utf-8', delay=False)
    except OSError:
        return None

    handler.setFormatter(logging.Formatter(FORMAT, datefmt='%Y-%m-%d %H:%M:%S'))
    LOGGER.addHandler(handler)
    LOGGER.info(f'arXorter v{__version__}, Python {platform.python_version()}, {platform.platform()}'
                f'{" (binary)" if getattr(sys, "frozen", False) else ""}')
    LOGGER.info(f'Arguments: {" ".join(argv) or "(none)"}')

    for old in log_files()[:-KEEP]:
        with contextlib.suppress(OSError):  # e.g. open in an editor, deleted next time
            old.unlink()
    return path
