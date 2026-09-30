"""
Check for updates and install them in background threads, so the window stays responsive.
"""
import contextlib
import threading

from PySide6.QtCore import QObject, QThread, Signal

from arxorter import __version__
from arxorter.updater import (
    Release,
    UpdateCancelled,
    UpdateError,
    find_update,
    get_system_name,
    install_update,
    latest_release,
)


class UpdateChecker(QObject):
    """
    Look for a newer release of the GUI in GitHub. Emits `checked` with the release (None if up to date) and the error
    message ('' if GitHub answered).

    The request runs in a daemon thread (not a QThread), so closing the window while GitHub has not answered yet does
    not have to wait for it.
    """
    checked = Signal(object, str)

    def start(self):
        threading.Thread(target=self.run, name='update-check', daemon=True).start()

    def run(self):
        release, message = None, ''
        try:
            release = find_update(latest_release(), get_system_name(), __version__, gui=True)
        except UpdateError as error:
            message = str(error)
        except Exception as error:  # Never let an unexpected answer of GitHub break the window
            message = f'Unable to check for updates: {error}'

        with contextlib.suppress(RuntimeError):  # The window was closed in the meantime
            self.checked.emit(release, message)


class UpdateInstaller(QThread):
    """
    Download the release and replace the installed program with it. Emits `progress` (bytes received and total) while
    downloading, then `installed` with the path of the new program, or `failed` with the error message ('' if it was
    cancelled).
    """
    progress = Signal(int, int)
    installed = Signal(object)
    failed = Signal(str)

    def __init__(self, release: Release, parent: QObject | None = None):
        super().__init__(parent)
        self.release = release
        self.cancel_requested = False

    def cancel(self):
        self.cancel_requested = True

    def _progress(self, received: int, total: int):
        if self.cancel_requested:
            raise UpdateCancelled
        self.progress.emit(received, total)

    def run(self):
        try:
            program = install_update(self.release, self._progress)
        except UpdateCancelled:
            self.failed.emit('')
        except UpdateError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f'Unable to install the new version: {error}')
        else:
            self.installed.emit(program)
