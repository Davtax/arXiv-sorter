"""
Scheduled run of arXiv-sorter (see arxiv_sorter.scheduler): no window, the settings saved by the window, and a
notification at the end. Clicking the notification opens the latest file written, or the log when the run failed.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from arxiv_sorter import __version__
from arxiv_sorter.gui.icons import app_icon
from arxiv_sorter.gui.settings import Settings
from arxiv_sorter.gui.summary import Outcome, WrittenFile, plural
from arxiv_sorter.gui.window import open_path, set_windows_app_id, settings_path, worker_command, worker_environment
from arxiv_sorter.log_file import latest_log
from arxiv_sorter.protocol import BUSY_EXIT_CODE, LOG_TAG, WRITTEN_TAG, Level
from arxiv_sorter.system import APP_NAME, NO_WINDOW, base_dir

NOTIFICATION_SECONDS = 20  # The notification can be clicked while the program waits, then it exits


def notification_text(outcome: Outcome, written: list[WrittenFile], first_error: str = '') -> tuple[str, str]:
    """
    Title and text of the notification shown at the end of the run.
    """
    if outcome is Outcome.FINISHED:
        if not written:
            return f'{APP_NAME}: nothing new', 'No new mailing lists to sort since the last run.'
        n_new = sum(file.n_new for file in written)
        return (f'{APP_NAME}: {plural(len(written), "mailing list")} sorted',
                f'{plural(n_new, "submission")} new or matching your keywords. Click to open the latest one.')
    detail = f'{first_error}\n' if first_error else ''
    sorted_lists = f'{plural(len(written), "mailing list")} sorted. ' if written else ''
    title = f'{APP_NAME}: finished with errors' if outcome is Outcome.ERRORS else f'{APP_NAME}: the daily run failed'
    return title, f'{detail}{sorted_lists}Click to open the log.'


class BackgroundRun(QObject):
    """
    Run the command line program in a separate process, as the window does, and notify its result.
    """

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.output = ''
        self.written: list[WrittenFile] = []
        self.first_error = ''
        self.tray: QSystemTrayIcon | None = None
        self.click_target: Path | None = None

        program, arguments = worker_command()
        self.process = QProcess(self)
        self.process.setProgram(program)
        self.process.setArguments(arguments + settings.to_cli_args())
        self.process.setProcessEnvironment(worker_environment())
        self.process.setWorkingDirectory(str(base_dir()))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.errorOccurred.connect(self.process_error)
        self.process.finished.connect(self.process_finished)

    def start(self):
        self.process.start()

    def read_output(self):
        self.output += bytes(self.process.readAllStandardOutput().data()).decode('utf-8', errors='replace')
        *lines, self.output = self.output.split('\n')
        for line in lines:
            self.handle_line(line.rstrip('\r'))

    def handle_line(self, line: str):
        if line.startswith(WRITTEN_TAG):
            written = WrittenFile.from_message(line.removeprefix(WRITTEN_TAG))
            if written is not None:
                self.written.append(written)
        elif line.startswith(f'{LOG_TAG}{Level.ERROR}\t') and not self.first_error:
            self.first_error = line.split('\t', 2)[-1]

    def process_error(self, error: QProcess.ProcessError):
        if error == QProcess.ProcessError.FailedToStart:
            self.first_error = f'Unable to start arXiv-sorter: {self.process.errorString()}'
            self.process_finished(-1, QProcess.ExitStatus.CrashExit)

    def process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        if self.output:
            self.handle_line(self.output)
            self.output = ''

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == BUSY_EXIT_CODE:
            self.notify(f'{APP_NAME}: daily run skipped', 'arXiv-sorter was already running, so the daily run was '
                        'skipped. It runs again tomorrow, or run it from the window.')
            return
        if exit_status == QProcess.ExitStatus.CrashExit:
            outcome = Outcome.FAILED
        elif exit_code != 0 or self.first_error:
            outcome = Outcome.ERRORS
        else:
            outcome = Outcome.FINISHED

        if outcome is Outcome.FINISHED:
            self.click_target = self.written[-1].path if self.written else None
        else:
            self.click_target = latest_log()
        self.notify(*notification_text(outcome, self.written, self.first_error))

    def notify(self, title: str, text: str):
        """
        Show the notification of the desktop, and exit a while later. On Linux, notify-send is preferred: the service
        started by systemd may have no display to show a tray icon.
        """
        notify_send = shutil.which('notify-send') if sys.platform.startswith('linux') else None
        if notify_send is not None or not QSystemTrayIcon.isSystemTrayAvailable():
            if notify_send is not None:
                subprocess.run([notify_send, '--app-name', APP_NAME, title, text], creationflags=NO_WINDOW)
            QApplication.quit()
            return

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        self.tray.messageClicked.connect(self.open_result)
        self.tray.activated.connect(self.open_result)
        self.tray.show()
        self.tray.showMessage(title, text, app_icon(), NOTIFICATION_SECONDS * 1000)
        QTimer.singleShot(NOTIFICATION_SECONDS * 1000, QApplication.quit)

    def open_result(self, *_):
        if self.click_target is not None:
            open_path(self.click_target)
        QApplication.quit()


def run_scheduled() -> int:
    if sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')  # Started by systemd without a display

    set_windows_app_id()  # The notification comes from arXiv-sorter, not from Python
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)  # There are no windows

    settings = Settings.load(settings_path(), base_dir())
    settings.custom_dates = False  # Every day, after the last mailing list saved
    run = BackgroundRun(settings)
    run.start()
    return app.exec()
