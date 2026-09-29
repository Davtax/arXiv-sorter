"""
Main window of the GUI. arXiv-sorter itself runs in a separate process, whose output is shown in the window.
"""
import codecs
import os
import sys
import time
from datetime import date
from pathlib import Path

from PySide6.QtCore import QByteArray, QDate, QProcess, QProcessEnvironment, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFontDatabase, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QDateEdit, QFileDialog, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget, )

from arxiv_sorter import __version__
from arxiv_sorter.gui.settings import SETTINGS_FILE, Settings
from arxiv_sorter.gui.summary import Outcome, WrittenFile, final_message
from arxiv_sorter.protocol import GUI_ENV_VAR, PROGRESS_TAG, QUESTION_TAG, WORKER_FLAG, WRITTEN_TAG
from arxiv_sorter.system import APP_NAME, base_dir, config_dir, is_frozen, kill_process_tree, max_threads

USER_FILES = ('keywords.txt', 'authors.txt', 'categories.txt')
PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # Folder that contains the arxiv_sorter package


def settings_path() -> Path:
    # Same folder as the pdffigures2 jar (see arxiv_sorter.system.config_dir)
    return config_dir() / SETTINGS_FILE


def worker_command() -> tuple[str, list[str]]:
    """
    Program and arguments to run arXiv-sorter in a separate process, so the GUI stays responsive and can stop it.
    """
    if is_frozen():  # The GUI binary also contains the command line program (see arxiv_sorter.gui.main)
        return sys.executable, [WORKER_FLAG]

    python = Path(sys.executable)
    pythonw = python.with_name('pythonw.exe')
    if os.name == 'nt' and pythonw.is_file():  # Avoid opening a console window on Windows
        python = pythonw

    return str(python), ['-m', 'arxiv_sorter']


def stop_process(process: QProcess):
    """
    Kill the worker process together with the programs it started (java, curl), which would keep running otherwise.
    """
    if process.processId() > 0:
        kill_process_tree(process.processId())
    process.kill()


class PathSelector(QWidget):
    """
    Line edit with buttons to browse for a directory and to open it in the file manager.
    """

    def __init__(self, dialog_title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.dialog_title = dialog_title

        self.line_edit = QLineEdit()
        browse_button = QPushButton('Browse…')
        browse_button.clicked.connect(self.browse)
        open_button = QPushButton('Open')
        open_button.setToolTip('Open the folder in the file manager')
        open_button.clicked.connect(self.open_folder)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.line_edit, stretch=1)
        layout.addWidget(browse_button)
        layout.addWidget(open_button)

    def path(self) -> str:
        return self.line_edit.text().strip()

    def set_path(self, path: str):
        self.line_edit.setText(path)

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, self.dialog_title, self.path())
        if folder:
            self.set_path(str(Path(folder)))

    def open_folder(self):
        folder = Path(self.path())
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} v{__version__}')

        self.settings_file = settings_path()
        self.process: QProcess | None = None
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.output_buffer = ''
        self.errors_found = False
        self.stop_requested = False
        self.written: list[WrittenFile] = []
        self.start_time = 0.0

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self._build_paths_group())
        options_row = QHBoxLayout()
        options_row.addWidget(self._build_dates_group(), stretch=1)
        options_row.addWidget(self._build_options_group(), stretch=1)
        layout.addLayout(options_row)
        layout.addLayout(self._build_run_row())
        layout.addWidget(self._build_log_group(), stretch=1)
        self.setCentralWidget(central)

        self.load_settings()

    # ---------------------------------------------------------------- widgets
    def _build_paths_group(self) -> QGroupBox:
        group = QGroupBox('Paths')
        form = QFormLayout(group)

        self.keywords_selector = PathSelector('Select the keywords directory')
        self.keywords_selector.setToolTip('Folder with keywords.txt, authors.txt and categories.txt (--directory)')
        form.addRow('Keywords directory:', self.keywords_selector)

        self.abstracts_selector = PathSelector('Select the abstracts directory')
        self.abstracts_selector.setToolTip('Folder where the Markdown files are written (--abstracts)')
        form.addRow('Abstracts directory:', self.abstracts_selector)

        files_row = QHBoxLayout()
        for filename in USER_FILES:
            button = QPushButton(f'Edit {filename}')
            button.setToolTip(f'Open {filename} with the default text editor (created if it does not exist)')
            button.clicked.connect(lambda _=False, name=filename: self.edit_user_file(name))
            files_row.addWidget(button)
        files_row.addStretch()
        form.addRow('Search files:', files_row)

        return group

    def _build_dates_group(self) -> QGroupBox:
        group = QGroupBox('Date range')
        grid = QGridLayout(group)

        self.auto_dates_radio = QRadioButton('Automatic: from the last saved abstracts until today')
        self.custom_dates_radio = QRadioButton('Custom range')
        self.auto_dates_radio.setChecked(True)
        self.custom_dates_radio.toggled.connect(self._update_dates_enabled)

        today = QDate.currentDate()
        self.date_0_edit = self._date_edit(today.addDays(-7))
        self.date_0_edit.setToolTip('First mailing date to request (--date0)')
        self.date_f_edit = self._date_edit(today)
        self.date_f_edit.setToolTip('Final date (--datef). Submissions are requested until the arXiv deadline '
                                    '(14:00 ET) of this day, so its own mailing is not included.')

        grid.addWidget(self.auto_dates_radio, 0, 0, 1, 4)
        grid.addWidget(self.custom_dates_radio, 1, 0, 1, 4)
        grid.addWidget(QLabel('From:'), 2, 0)
        grid.addWidget(self.date_0_edit, 2, 1)
        grid.addWidget(QLabel('Until:'), 2, 2)
        grid.addWidget(self.date_f_edit, 2, 3)
        grid.setRowStretch(3, 1)

        self._update_dates_enabled()
        return group

    @staticmethod
    def _date_edit(value: QDate) -> QDateEdit:
        edit = QDateEdit(value)
        edit.setCalendarPopup(True)
        edit.setDisplayFormat('yyyy-MM-dd')
        edit.setMaximumDate(QDate.currentDate())
        return edit

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox('Options')
        box = QVBoxLayout(group)

        self.images_check = QCheckBox('Include figures (download the PDFs and extract the first figure)')
        self.final_date_check = QCheckBox('Add the final timestamp to the Markdown file')
        self.separate_check = QCheckBox('Create a separate file for each manuscript')
        self.sort_authors_check = QCheckBox('Sort the authors file and remove blank lines')
        self.update_check = QCheckBox('Download new versions of arXiv-sorter when available')
        self.update_check.setVisible(False)  # Temporarily disabled: the update is not implemented yet
        self.verbose_check = QCheckBox('Verbose output')

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, max_threads())
        self.threads_spin.setToolTip(f'Threads to detect the figures, up to {max_threads()} (CPUs of this system). '
                                     'More threads are faster, but use more memory (--threads)')
        self.images_check.toggled.connect(self._update_threads_enabled)
        threads_row = QHBoxLayout()
        threads_row.setContentsMargins(24, 0, 0, 0)  # Indented below "Include figures", which it depends on
        threads_row.addWidget(QLabel('Threads to detect the figures:'))
        threads_row.addWidget(self.threads_spin)
        threads_row.addStretch()

        box.addWidget(self.images_check)
        box.addLayout(threads_row)
        for check in (self.final_date_check, self.separate_check, self.sort_authors_check, self.update_check,
                      self.verbose_check):
            box.addWidget(check)
        box.addStretch()

        return group

    def _build_run_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.run_button = QPushButton('Run')
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.start)
        self.stop_button = QPushButton('Stop')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)

        self.status_label = QLabel('Ready')
        self.status_label.setMinimumWidth(200)

        row.addWidget(self.run_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.progress_bar, stretch=1)
        row.addWidget(self.status_label, stretch=1)
        return row

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox('Messages')
        box = QVBoxLayout(group)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(20000)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        clear_button = QPushButton('Clear messages')
        clear_button.clicked.connect(self.log.clear)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(clear_button)

        box.addWidget(self.log)
        box.addLayout(buttons)
        return group

    def _update_threads_enabled(self):
        self.threads_spin.setEnabled(self.images_check.isChecked() and self.run_button.isEnabled())

    def _update_dates_enabled(self):
        custom = self.custom_dates_radio.isChecked()
        self.date_0_edit.setEnabled(custom)
        self.date_f_edit.setEnabled(custom)

    # --------------------------------------------------------------- settings
    def current_settings(self) -> Settings:
        return Settings(keywords_dir=self.keywords_selector.path(), abstracts_dir=self.abstracts_selector.path(),
                        images=self.images_check.isChecked(), threads=self.threads_spin.value(),
                        final_date=self.final_date_check.isChecked(), separate=self.separate_check.isChecked(),
                        sort_authors=self.sort_authors_check.isChecked(), update=False,
                        verbose=self.verbose_check.isChecked(), custom_dates=self.custom_dates_radio.isChecked(),
                        date_0=self.date_0_edit.date().toString(Qt.DateFormat.ISODate),
                        date_f=self.date_f_edit.date().toString(Qt.DateFormat.ISODate),
                        window_geometry=self.saveGeometry().toBase64().data().decode('ascii'), )

    def load_settings(self):
        settings = Settings.load(self.settings_file, base_dir())

        self.keywords_selector.set_path(settings.keywords_dir)
        self.abstracts_selector.set_path(settings.abstracts_dir)
        self.images_check.setChecked(settings.images)
        self.threads_spin.setValue(settings.threads)
        self._update_threads_enabled()
        self.final_date_check.setChecked(settings.final_date)
        self.separate_check.setChecked(settings.separate)
        self.sort_authors_check.setChecked(settings.sort_authors)
        self.update_check.setChecked(settings.update)
        self.verbose_check.setChecked(settings.verbose)
        self.custom_dates_radio.setChecked(settings.custom_dates)
        self.auto_dates_radio.setChecked(not settings.custom_dates)

        for edit, value in ((self.date_0_edit, settings.date_0), (self.date_f_edit, settings.date_f)):
            saved_date = QDate.fromString(value, Qt.DateFormat.ISODate)
            if saved_date.isValid():
                edit.setDate(min(saved_date, QDate.currentDate()))

        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(settings.window_geometry.encode('ascii')))
        else:
            self.resize(950, 700)

    def save_settings(self):
        try:
            self.current_settings().save(self.settings_file)
        except OSError as error:
            self.append_log(f'Unable to save the settings in {self.settings_file}: {error}')

    # ------------------------------------------------------------ user files
    def edit_user_file(self, filename: str):
        folder = self.keywords_selector.path()
        if not folder:
            QMessageBox.warning(self, APP_NAME, 'Select the keywords directory first.')
            return

        file = Path(folder) / filename
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.touch(exist_ok=True)
        except OSError as error:
            QMessageBox.warning(self, APP_NAME, f'Unable to create {file}: {error}')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(file.resolve())))

    # ---------------------------------------------------------------- running
    def validate(self, settings: Settings) -> str | None:
        """
        Error message for invalid settings, or None if they are valid.
        """
        if not settings.keywords_dir:
            return 'Select the keywords directory.'
        if not settings.abstracts_dir:
            return 'Select the abstracts directory.'
        if settings.custom_dates and date.fromisoformat(settings.date_0) >= date.fromisoformat(settings.date_f):
            return 'The "From" date must be earlier than the "Until" date.'
        return None

    def start(self):
        if self.process is not None:
            return

        settings = self.current_settings()
        error = self.validate(settings)
        if error is not None:
            QMessageBox.warning(self, APP_NAME, error)
            return
        self.save_settings()

        program, arguments = worker_command()
        arguments += settings.to_cli_args()

        environment = QProcessEnvironment.systemEnvironment()
        environment.insert(GUI_ENV_VAR, '1')
        environment.insert('PYTHONUNBUFFERED', '1')
        environment.insert('PYTHONIOENCODING', 'utf-8')
        if not is_frozen():  # Make the package importable by the worker, even if it is not installed
            python_path = [str(PACKAGE_ROOT), environment.value('PYTHONPATH')]
            environment.insert('PYTHONPATH', os.pathsep.join(filter(None, python_path)))

        self.process = QProcess(self)
        self.process.setProgram(program)
        self.process.setArguments(arguments)
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(base_dir()))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.errorOccurred.connect(self.process_error)
        self.process.finished.connect(self.process_finished)

        self.decoder.reset()
        self.output_buffer = ''
        self.errors_found = False
        self.stop_requested = False
        self.written = []
        self.start_time = time.monotonic()

        if settings.verbose:
            self.append_log('$ ' + ' '.join([program, *arguments]))
        self.set_running(True)
        self.set_busy('Starting …')
        self.process.start()

    def stop(self):
        if self.process is None:
            return
        self.append_log('Stopping arXiv-sorter …')
        self.stop_requested = True
        stop_process(self.process)

    def set_running(self, running: bool):
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        for widget in (self.keywords_selector, self.abstracts_selector, self.auto_dates_radio, self.custom_dates_radio,
                       self.images_check, self.final_date_check, self.separate_check, self.sort_authors_check,
                       self.verbose_check):
            widget.setEnabled(not running)
        self._update_threads_enabled()
        if running:
            self.date_0_edit.setEnabled(False)
            self.date_f_edit.setEnabled(False)
        else:
            self._update_dates_enabled()

    def set_busy(self, status: str | None = None):
        self.progress_bar.setRange(0, 0)  # Indeterminate
        if status is not None:
            self.status_label.setText(status)

    def append_log(self, text: str):
        self.log.appendPlainText(text)
        scroll_bar = self.log.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def read_output(self):
        data = self.process.readAllStandardOutput().data()
        self.output_buffer += self.decoder.decode(data)

        *lines, self.output_buffer = self.output_buffer.split('\n')
        for line in lines:
            self.handle_line(line)

    def handle_line(self, line: str):
        line = line.rstrip('\r').rsplit('\r', 1)[-1]  # Keep only the last state of lines rewritten with \r

        if line.startswith(PROGRESS_TAG):
            self.update_progress(line.removeprefix(PROGRESS_TAG))
        elif line.startswith(QUESTION_TAG):
            self.ask_question(line.removeprefix(QUESTION_TAG))
        elif line.startswith(WRITTEN_TAG):
            written = WrittenFile.from_message(line.removeprefix(WRITTEN_TAG))
            if written is not None:
                self.written.append(written)
        else:
            if line.startswith('An error occurred'):
                self.errors_found = True
            self.append_log(line)
            if line.strip() and not set(line.strip()) <= {'-'}:
                self.status_label.setText(line.strip())

    def update_progress(self, message: str):
        try:
            current, count, prefix = message.split('\t', 2)
            current, count = int(current), int(count)
        except ValueError:
            return

        if current >= count:  # Wait for the next step
            self.set_busy()
            return

        self.progress_bar.setRange(0, count)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f'{prefix.rstrip(":")} %v/%m')
        self.status_label.setText(prefix.rstrip(':'))

    def ask_question(self, message: str):
        answer = QMessageBox.question(self, APP_NAME, message)
        reply = 'y' if answer == QMessageBox.StandardButton.Yes else 'n'
        self.process.write(f'{reply}\n'.encode())

    def process_error(self, error: QProcess.ProcessError):
        if error == QProcess.ProcessError.FailedToStart:
            self.append_log(f'Unable to start arXiv-sorter: {self.process.errorString()}')
            self.errors_found = True
            self.process_finished(-1, QProcess.ExitStatus.CrashExit)

    def process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        if self.process is None:
            return

        if self.output_buffer:
            self.handle_line(self.output_buffer)
            self.output_buffer = ''

        self.process.deleteLater()
        self.process = None
        self.set_running(False)

        if self.stop_requested:
            outcome = Outcome.STOPPED
        elif exit_status == QProcess.ExitStatus.CrashExit:
            outcome = Outcome.FAILED
        elif exit_code != 0 or self.errors_found:
            outcome = Outcome.ERRORS
        else:
            outcome = Outcome.FINISHED

        self.progress_bar.setRange(0, 1)
        self.progress_bar.setFormat('%p%')
        self.progress_bar.setValue(1 if outcome is Outcome.FINISHED else 0)

        status, lines = final_message(outcome, time.monotonic() - self.start_time, self.written)
        for line in lines:
            self.append_log(line)
        self.status_label.setText(status)
        QApplication.alert(self)  # Flash the taskbar entry (Dock icon on macOS) if the window is not active

    def closeEvent(self, event: QCloseEvent):
        if self.process is not None:
            answer = QMessageBox.question(self, APP_NAME, 'arXiv-sorter is still running. Stop it and exit?')
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            stop_process(self.process)
            self.process.waitForFinished(3000)

        self.save_settings()
        event.accept()


def start_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon.fromTheme('document-open'))

    window = MainWindow()
    window.show()
    return app.exec()
