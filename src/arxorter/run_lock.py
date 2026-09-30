"""
Only one run of arXorter at a time, whether it is started from a terminal, from the window or by the daily
schedule: two runs would write the same mailing lists and sort authors.txt at the same time.

The lock is a lock of the operating system on a file of the configuration folder, so it is released when the process
ends, also when it crashes or is killed, and never stays behind.
"""
import contextlib
import sys
from pathlib import Path
from typing import IO

from arxorter.system import config_dir

LOCK_FILE = 'run.lock'


def lock_path() -> Path:
    return config_dir() / LOCK_FILE


class RunLock:
    def __init__(self, path: Path | None = None):
        self.path = path or lock_path()
        self.file: IO[bytes] | None = None

    def acquire(self) -> bool:
        """
        Take the lock, without waiting. False if another run holds it.
        """
        if self.file is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = open(self.path, 'a+b')  # noqa: SIM115  # Kept open while the lock is held
        try:
            _lock(file)
        except OSError:
            file.close()
            return False
        self.file = file
        return True

    def release(self):
        if self.file is None:
            return
        with contextlib.suppress(OSError):  # Released anyway when the file is closed
            _unlock(self.file)
        self.file.close()
        self.file = None

    def __enter__(self) -> RunLock:
        return self

    def __exit__(self, *_):
        self.release()


def is_running(path: Path | None = None) -> bool:
    """
    Whether another run of arXorter holds the lock.
    """
    lock = RunLock(path)
    if not lock.acquire():
        return True
    lock.release()
    return False


if sys.platform == 'win32':
    import msvcrt

    def _lock(file: IO[bytes]):
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(file: IO[bytes]):
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(file: IO[bytes]):
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(file: IO[bytes]):
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
