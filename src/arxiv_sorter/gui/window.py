"""
Main window of the GUI. arXiv-sorter itself runs in a separate process, whose messages are shown in the window.
"""
import codecs
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QDate, QEvent, QProcess, QProcessEnvironment, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from arxiv_sorter import __version__
from arxiv_sorter.gui.icons import app_icon, run_icon, stop_icon
from arxiv_sorter.gui.log_view import COLORS, LogView, is_dark
from arxiv_sorter.gui.search_editor import SearchFilesEditor
from arxiv_sorter.gui.search_files import SEARCH_FILES, count_terms, describe
from arxiv_sorter.gui.settings import SETTINGS_FILE, THEMES, Settings
from arxiv_sorter.gui.summary import Outcome, WrittenFile, final_message, format_duration
from arxiv_sorter.gui.theme import apply_theme
from arxiv_sorter.log_file import latest_log, logs_dir
from arxiv_sorter.protocol import GUI_ENV_VAR, LOG_TAG, PROGRESS_TAG, QUESTION_TAG, WORKER_FLAG, WRITTEN_TAG, Level
from arxiv_sorter.search_terms import Kind, Problem, Severity, check_file, check_folder
from arxiv_sorter.system import APP_NAME, base_dir, config_dir, is_frozen, kill_process_tree, max_threads

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # Folder that contains the arxiv_sorter package
REPOSITORY_URL = 'https://github.com/Davtax/arXiv-sorter'
WINDOWS_APP_ID = 'Davtax.arXiv-sorter.GUI'  # Identity of the application in the Windows taskbar
DATE_FORMAT = 'ddd d MMM yyyy'  # e.g. Tue 22 Sep 2026
THREADS_EXTRA_INDENT = 20  # Pixels beyond the text of "Include the first figure", to show the threads belong to it

THEME_NAMES = {'system': 'System', 'light': 'Light', 'dark': 'Dark'}
THEME_ICONS = {'system': '🌓', 'light': '☀️', 'dark': '🌙'}
THEME_TOOLTIPS = {'system': 'Follow the light or dark mode of the operating system', 'light': 'Always light',
                  'dark': 'Always dark'}


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


def open_path(path: Path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_url(url: str):
    QDesktopServices.openUrl(QUrl(url))


def ensure_dir(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def hint_label(text: str) -> QLabel:
    """
    Small secondary text, to explain an option.
    """
    label = QLabel(text)
    label.setWordWrap(True)
    label.setEnabled(False)  # Shown with the muted color of the style
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 0.9)
    label.setFont(font)
    return label


class PathSelector(QWidget):
    """
    Line edit with buttons to browse for a directory and to open it in the file manager.
    """

    def __init__(self, dialog_title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.dialog_title = dialog_title

        self.line_edit = QLineEdit()
        self.line_edit.setClearButtonEnabled(True)
        browse_button = QPushButton('Browse…')
        browse_button.setToolTip('Choose the folder')
        browse_button.clicked.connect(self.browse)
        open_button = QToolButton()
        open_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
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
        if not self.path():
            return
        folder = Path(self.path())
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder.resolve())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} v{__version__}')
        self.setWindowIcon(app_icon())
        self.setMinimumSize(760, 600)

        self.settings_file = settings_path()
        self.process: QProcess | None = None
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.output_buffer = ''
        self.errors_found = False
        self.n_warnings = 0
        self.stop_requested = False
        self.written: list[WrittenFile] = []
        self.start_time = 0.0
        self.theme = 'system'

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_elapsed)
        self.search_files_timer = QTimer(self)  # Refresh the counts once the user stops typing the folder
        self.search_files_timer.setSingleShot(True)
        self.search_files_timer.setInterval(400)
        self.search_files_timer.timeout.connect(self.refresh_search_files)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.addWidget(self._build_folders_group())
        options_row = QHBoxLayout()
        options_row.addWidget(self._build_dates_group(), stretch=1)
        options_row.addWidget(self._build_options_group(), stretch=1)
        layout.addLayout(options_row)
        layout.addLayout(self._build_run_row())
        layout.addWidget(self._build_messages_group(), stretch=1)
        self.setCentralWidget(central)

        self._build_menus()
        self._build_status_bar()
        self.load_settings()
        self.refresh_search_files()

    # ---------------------------------------------------------------- widgets
    def _build_folders_group(self) -> QGroupBox:
        group = QGroupBox('📁  Folders')
        form = QFormLayout(group)

        self.keywords_selector = PathSelector('Select the folder with the search files')
        self.keywords_selector.setToolTip('Folder with keywords.txt, authors.txt and categories.txt (--directory)')
        self.keywords_selector.line_edit.textChanged.connect(lambda: self.search_files_timer.start())
        form.addRow('Search files:', self.keywords_selector)

        files_row = QHBoxLayout()
        self.search_file_labels: dict[str, QLabel] = {}
        for search_file in SEARCH_FILES:
            label = QLabel()
            self.search_file_labels[search_file.filename] = label
            button = QToolButton()
            button.setText('Edit')
            button.setToolTip(f'Edit {search_file.filename}, checking the mistakes while you type, and preview the '
                              'submissions it would find')
            button.clicked.connect(lambda _=False, name=search_file.filename: self.edit_user_file(name))
            files_row.addWidget(label)
            files_row.addWidget(button)
            files_row.addSpacing(12)
        files_row.addStretch()
        form.addRow('', files_row)

        self.abstracts_selector = PathSelector('Select the folder for the abstracts')
        self.abstracts_selector.setToolTip('Folder where the Markdown files are saved, e.g. inside your Obsidian '
                                           'vault (--abstracts)')
        form.addRow('Abstracts:', self.abstracts_selector)

        return group

    def _build_dates_group(self) -> QGroupBox:
        group = QGroupBox('📅  Date range')
        grid = QGridLayout(group)

        self.auto_dates_radio = QRadioButton('Automatic')
        self.auto_dates_radio.setToolTip('Continue after the last mailing list saved in the abstracts folder')
        self.custom_dates_radio = QRadioButton('Custom range')
        self.custom_dates_radio.setToolTip('Choose the mailing lists to request (--date0 and --datef)')
        self.auto_dates_radio.setChecked(True)
        self.custom_dates_radio.toggled.connect(self._update_dates_enabled)

        today = QDate.currentDate()
        self.date_0_edit = self._date_edit(today.addDays(-7))
        self.date_0_edit.setToolTip('First mailing list to request (--date0)')
        self.date_f_edit = self._date_edit(today)
        self.date_f_edit.setToolTip('Submissions are requested until the arXiv deadline (14:00 ET) of this day, so its '
                                    'own mailing list is not included (--datef)')

        grid.addWidget(self.auto_dates_radio, 0, 0, 1, 4)
        grid.addWidget(hint_label('Continues after the last mailing list saved in the abstracts folder.'), 1, 0, 1, 4)
        grid.addWidget(self.custom_dates_radio, 2, 0, 1, 4)
        self.date_0_label = QLabel('From')
        self.date_f_label = QLabel('until')
        grid.addWidget(self.date_0_label, 3, 0)
        grid.addWidget(self.date_0_edit, 3, 1)
        grid.addWidget(self.date_f_label, 3, 2)
        grid.addWidget(self.date_f_edit, 3, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setRowStretch(4, 1)

        self._update_dates_enabled()
        return group

    @staticmethod
    def _date_edit(value: QDate) -> QDateEdit:
        edit = QDateEdit(value)
        edit.setCalendarPopup(True)
        edit.setDisplayFormat(DATE_FORMAT)
        edit.setMaximumDate(QDate.currentDate())
        return edit

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox('⚙️  Options')
        box = QVBoxLayout(group)

        self.images_check = QCheckBox('Include the first figure of each new submission')
        self.images_check.setToolTip('Download the PDFs and extract their first figure (needs Java). Slower, and '
                                     'arXiv may limit the downloads (untick for --image)')
        self.final_date_check = QCheckBox('Add a timestamp at the end of the Markdown file')
        self.final_date_check.setToolTip('Untick for --final')
        self.separate_check = QCheckBox('Create a separate file for each submission')
        self.separate_check.setToolTip('A folder per mailing list, with a Markdown file per submission (--separate)')
        self.sort_authors_check = QCheckBox('Sort authors.txt and remove its blank lines')
        self.sort_authors_check.setToolTip('Untick for --modify')
        self.update_check = QCheckBox('Download new versions of arXiv-sorter when available')
        self.update_check.setVisible(False)  # Temporarily disabled: the update is not implemented yet
        self.verbose_check = QCheckBox('Show detailed messages')
        self.verbose_check.setToolTip('Useful to understand a problem (--verbose)')

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, max_threads())
        self.threads_spin.setToolTip(f'Threads to detect the figures, up to {max_threads()} (CPUs of this system). '
                                     'More threads are faster, but use more memory (--threads)')
        self.images_check.toggled.connect(self._update_threads_enabled)
        threads_row = QHBoxLayout()
        # Indented past the text of the figures option, which it depends on (measured with the style of the platform)
        text_start = (self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth)
                      + self.style().pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing))
        threads_row.setContentsMargins(text_start + THREADS_EXTRA_INDENT, 0, 0, 0)
        self.threads_label = QLabel('Threads to detect them:')
        threads_row.addWidget(self.threads_label)
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

        self.run_button = QPushButton('  Run')
        self.run_button.setIcon(run_icon())
        self.run_button.setToolTip('Request, sort and save the new submissions (Ctrl+R)')
        self.run_button.setShortcut(QKeySequence('Ctrl+R'))
        self.run_button.setDefault(True)
        self.run_button.setMinimumHeight(38)
        self.run_button.setMinimumWidth(110)
        font = self.run_button.font()
        font.setBold(True)
        self.run_button.setFont(font)
        self.run_button.clicked.connect(self.start)

        self.stop_button = QPushButton('  Stop')
        self.stop_button.setIcon(stop_icon())
        self.stop_button.setToolTip('Stop arXiv-sorter. The mailing lists already saved are kept')
        self.stop_button.setMinimumHeight(38)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)

        self.stage_label = QLabel('Ready when you are 🙂')
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        progress_box = QVBoxLayout()
        progress_box.setSpacing(2)
        progress_box.addWidget(self.stage_label)
        progress_box.addWidget(self.progress_bar)

        row.addWidget(self.run_button)
        row.addWidget(self.stop_button)
        row.addSpacing(8)
        row.addLayout(progress_box, stretch=1)
        return row

    def _build_messages_group(self) -> QGroupBox:
        group = QGroupBox('💬  Messages')
        box = QVBoxLayout(group)

        self.log = LogView()
        font = self.log.font()
        font.setStyleHint(QFont.StyleHint.SansSerif)
        self.log.setFont(font)

        self.open_latest_button = QPushButton('📖  Open the latest file')
        self.open_latest_button.setToolTip('Open the last Markdown file saved, e.g. in Obsidian')
        self.open_latest_button.setEnabled(False)
        self.open_latest_button.clicked.connect(self.open_latest_file)
        open_folder_button = QPushButton('📂  Open the abstracts folder')
        open_folder_button.clicked.connect(self.abstracts_selector.open_folder)

        copy_button = QToolButton()
        copy_button.setText('Copy')
        copy_button.setToolTip('Copy the messages to the clipboard, e.g. to report a problem')
        copy_button.clicked.connect(self.copy_messages)
        save_button = QToolButton()
        save_button.setText('Save…')
        save_button.setToolTip('Save the messages in a text file')
        save_button.clicked.connect(self.save_messages)
        clear_button = QToolButton()
        clear_button.setText('Clear')
        clear_button.clicked.connect(self.log.clear)

        buttons = QHBoxLayout()
        buttons.addWidget(self.open_latest_button)
        buttons.addWidget(open_folder_button)
        buttons.addStretch()
        for button in (copy_button, save_button, clear_button):
            buttons.addWidget(button)

        box.addWidget(self.log)
        box.addLayout(buttons)
        return group

    def _build_menus(self):
        file_menu = self.menuBar().addMenu('&File')
        self._add_action(file_menu, 'Open the abstracts folder', self.abstracts_selector.open_folder, 'Ctrl+O')
        self._add_action(file_menu, 'Open the settings folder', lambda: open_path(config_dir()))
        file_menu.addSeparator()
        self._add_action(file_menu, 'Save the messages…', self.save_messages, QKeySequence.StandardKey.Save)
        file_menu.addSeparator()
        self._add_action(file_menu, 'Quit', self.close, QKeySequence.StandardKey.Quit).setMenuRole(
            QAction.MenuRole.QuitRole)

        view_menu = self.menuBar().addMenu('&View')
        self.theme_menu = view_menu.addMenu('Theme')
        self.theme_actions = QActionGroup(self)  # Only one of them is checked
        for theme in THEMES:
            action = QAction(THEME_NAMES[theme], self, checkable=True)
            action.setToolTip(THEME_TOOLTIPS[theme])
            action.triggered.connect(lambda _=False, name=theme: self.set_theme(name))
            self.theme_actions.addAction(action)
            self.theme_menu.addAction(action)

        help_menu = self.menuBar().addMenu('&Help')
        self._add_action(help_menu, 'User guide', lambda: open_url(f'{REPOSITORY_URL}#readme'),
                         QKeySequence.StandardKey.HelpContents)
        self._add_action(help_menu, 'Report a problem', lambda: open_url(f'{REPOSITORY_URL}/issues'))
        help_menu.addSeparator()
        self._add_action(help_menu, 'Open the log of the last run', self.open_latest_log)
        self._add_action(help_menu, 'Open the logs folder', lambda: open_path(ensure_dir(logs_dir())))
        help_menu.addSeparator()
        self._add_action(help_menu, f'About {APP_NAME}', self.show_about).setMenuRole(QAction.MenuRole.AboutRole)

    def _add_action(self, menu, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_status_bar(self):
        self.elapsed_label = QLabel()
        self.theme_button = QToolButton()  # Same choices as View → Theme, easier to find
        self.theme_button.setMenu(self.theme_menu)
        self.theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.theme_button.setAutoRaise(True)
        self.theme_button.setToolTip('Light or dark theme')
        self.statusBar().addPermanentWidget(self.elapsed_label)
        self.statusBar().addPermanentWidget(self.theme_button)
        self.statusBar().showMessage('Ready')

    def set_theme(self, theme: str, save: bool = True):
        """
        Apply the theme (one of THEMES), and remember it for the next time.
        """
        self.theme = theme
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme)
        for action, name in zip(self.theme_actions.actions(), THEMES, strict=True):
            action.setChecked(name == theme)
        self.theme_button.setText(f'{THEME_ICONS[theme]} {THEME_NAMES[theme]}')
        self.refresh_search_files()  # Their warning colors depend on the theme
        if save:
            self.save_settings()

    def _update_threads_enabled(self):
        enabled = self.images_check.isChecked() and self.run_button.isEnabled()
        self.threads_spin.setEnabled(enabled)
        self.threads_label.setEnabled(enabled)

    def _update_dates_enabled(self):
        # The dates (and their labels) only matter for a custom range, and cannot change during a run
        enabled = self.custom_dates_radio.isChecked() and self.process is None
        for widget in (self.date_0_label, self.date_0_edit, self.date_f_label, self.date_f_edit):
            widget.setEnabled(enabled)

    def _update_elapsed(self):
        self.elapsed_label.setText(f'⏱ {format_duration(time.monotonic() - self.start_time)}')

    # --------------------------------------------------------------- settings
    def current_settings(self) -> Settings:
        return Settings(keywords_dir=self.keywords_selector.path(), abstracts_dir=self.abstracts_selector.path(),
                        images=self.images_check.isChecked(), threads=self.threads_spin.value(),
                        final_date=self.final_date_check.isChecked(), separate=self.separate_check.isChecked(),
                        sort_authors=self.sort_authors_check.isChecked(), update=False,
                        verbose=self.verbose_check.isChecked(), custom_dates=self.custom_dates_radio.isChecked(),
                        date_0=self.date_0_edit.date().toString(Qt.DateFormat.ISODate),
                        date_f=self.date_f_edit.date().toString(Qt.DateFormat.ISODate), theme=self.theme,
                        window_geometry=bytes(self.saveGeometry().toBase64().data()).decode('ascii'), )

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
            self.resize(1000, 780)
        self.set_theme(settings.theme, save=False)

    def save_settings(self):
        try:
            self.current_settings().save(self.settings_file)
        except OSError as error:
            self.log.add_message(Level.WARNING, f'Unable to save the settings in {self.settings_file}: {error}', '⚠️')

    # ------------------------------------------------------------ user files
    def refresh_search_files(self):
        """
        Count the terms of each search file, and flag the files with mistakes (details in the tooltip).
        """
        folder = Path(self.keywords_selector.path()) if self.keywords_selector.path() else None
        for search_file in SEARCH_FILES:
            label = self.search_file_labels[search_file.filename]
            if folder is None:
                label.setText(describe(search_file, None))
                label.setToolTip('')
                label.setStyleSheet('')
                continue

            path = folder / search_file.filename
            problems = check_file(path, Kind(path.stem))
            errors = [problem for problem in problems if problem.severity is Severity.ERROR]
            text = describe(search_file, count_terms(path))
            tooltip = str(path)
            if problems:
                text = f'{"❌" if errors else "⚠️"} {text}'
                tooltip += '\n\n' + '\n'.join(str(problem) for problem in problems)
            label.setText(text)
            label.setToolTip(tooltip)
            level = Level.ERROR if errors else Level.WARNING if problems else None
            color = COLORS[is_dark(self.palette())].get(level) if level is not None else None
            label.setStyleSheet(f'color: {color}; font-weight: bold' if color else '')

    def confirm_search_files(self) -> bool:
        """
        Before a run: True if the search files have no mistakes. Otherwise they are listed, with the option to edit
        the first file with mistakes.
        """
        errors = self.search_file_errors()
        if not errors:
            return True

        box = QMessageBox(QMessageBox.Icon.Warning, APP_NAME, 'The search files have mistakes, so arXiv-sorter '
                          'would stop before sorting. Fix them first:', parent=self)
        box.setInformativeText('\n'.join(f'• {problem}' for problem in errors))
        edit_button = box.addButton(f'Edit {errors[0].filename}', QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is edit_button:
            self.edit_user_file(errors[0].filename, errors[0].line)
        return False

    def search_file_errors(self) -> list[Problem]:
        folder = self.keywords_selector.path()
        if not folder:
            return []
        return [problem for problem in check_folder(Path(folder)) if problem.severity is Severity.ERROR]

    def edit_user_file(self, filename: str, line: int | None = None):
        """
        Open the editor of the search files on the given file (and line).
        """
        folder = self.keywords_selector.path()
        if not folder:
            QMessageBox.information(self, APP_NAME, 'Choose the folder of the search files first.')
            return

        editor = SearchFilesEditor(Path(folder).resolve(), self)
        editor.open_file(filename, line)
        editor.exec()
        self.refresh_search_files()

    def open_latest_log(self):
        path = latest_log()
        if path is None:
            QMessageBox.information(self, APP_NAME, 'There are no log files yet. One is written each time '
                                    'arXiv-sorter runs.')
            return
        open_path(path)

    def open_latest_file(self):
        if self.written:
            open_path(self.written[-1].path)

    def copy_messages(self):
        QApplication.clipboard().setText(self.log.toPlainText())
        self.statusBar().showMessage('Messages copied to the clipboard', 3000)

    def save_messages(self):
        folder = Path(self.abstracts_selector.path() or base_dir())
        default = folder / f'arXiv-sorter {datetime.now():%Y-%m-%d %H%M}.txt'
        path, _ = QFileDialog.getSaveFileName(self, 'Save the messages', str(default), 'Text files (*.txt)')
        if not path:
            return
        try:
            Path(path).write_text(self.log.toPlainText(), encoding='utf-8')
        except OSError as error:
            QMessageBox.warning(self, APP_NAME, f'Unable to save the messages:\n{error}')
            return
        self.statusBar().showMessage(f'Messages saved in {path}', 5000)

    def show_about(self):
        QMessageBox.about(
            self, f'About {APP_NAME}',
            f'<h3>{APP_NAME} v{__version__}</h3>'
            '<p>Download, sort and highlight the daily arXiv submissions matching your keywords and authors, as '
            'Markdown files for Obsidian.</p>'
            f'<p><a href="{REPOSITORY_URL}">{REPOSITORY_URL}</a></p>'
            f'<p>Settings and pdffigures2 are kept in<br><a href="{QUrl.fromLocalFile(str(config_dir())).toString()}">'
            f'{config_dir()}</a></p>'
            '<p>MIT License</p>')

    # ---------------------------------------------------------------- running
    def validate(self, settings: Settings) -> str | None:
        """
        Error message for invalid settings, or None if they are valid.
        """
        if not settings.keywords_dir:
            return 'Choose the folder of the search files (keywords, authors and categories).'
        if not settings.abstracts_dir:
            return 'Choose the folder where the abstracts are saved.'
        if settings.custom_dates and date.fromisoformat(settings.date_0) >= date.fromisoformat(settings.date_f):
            return 'The "From" date must be earlier than the "until" date.'
        return None

    def start(self):
        if self.process is not None:
            return

        settings = self.current_settings()
        error = self.validate(settings)
        if error is not None:
            QMessageBox.information(self, APP_NAME, error)
            return
        if not self.confirm_search_files():
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
        self.n_warnings = 0
        self.stop_requested = False
        self.written = []
        self.open_latest_button.setEnabled(False)
        self.start_time = time.monotonic()

        self.log.clear()
        if settings.verbose:
            self.log.add_message(Level.DETAIL, '$ ' + ' '.join([program, *arguments]))
        self.set_running(True)
        self.set_stage('🚀 Starting …')
        self._update_elapsed()
        self.elapsed_timer.start()
        self.process.start()

    def stop(self):
        if self.process is None:
            return
        self.log.add_message(Level.WARNING, 'Stopping arXiv-sorter …', '🛑')
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
        self._update_dates_enabled()

    def set_stage(self, text: str):
        """
        Show what arXiv-sorter is doing, with a busy progress bar until the next progress update.
        """
        self.stage_label.setText(text)
        self.statusBar().showMessage(text)
        self.progress_bar.setRange(0, 0)

    def read_output(self):
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput().data())
        self.output_buffer += self.decoder.decode(data)

        *lines, self.output_buffer = self.output_buffer.split('\n')
        for line in lines:
            self.handle_line(line)

    def handle_line(self, line: str):
        line = line.rstrip('\r').rsplit('\r', 1)[-1]  # Keep only the last state of lines rewritten with \r

        if line.startswith(LOG_TAG):
            self.handle_message(line.removeprefix(LOG_TAG))
        elif line.startswith(PROGRESS_TAG):
            self.update_progress(line.removeprefix(PROGRESS_TAG))
        elif line.startswith(QUESTION_TAG):
            self.ask_question(line.removeprefix(QUESTION_TAG))
        elif line.startswith(WRITTEN_TAG):
            written = WrittenFile.from_message(line.removeprefix(WRITTEN_TAG))
            if written is not None:
                self.written.append(written)
                self.open_latest_button.setEnabled(True)
        elif line.strip():
            self.log.add_plain(line)

    def handle_message(self, message: str):
        try:
            level_name, icon, text = message.split('\t', 2)
            level = Level(level_name)
        except ValueError:
            self.log.add_plain(message)
            return

        self.log.add_message(level, text, icon)
        if level is Level.ERROR:
            self.errors_found = True
        elif level is Level.WARNING:
            self.n_warnings += 1
        if level in (Level.STEP, Level.INFO) and text:
            self.set_stage(f'{icon} {text}'.strip())

    def update_progress(self, message: str):
        try:
            current_text, count_text, prefix = message.split('\t', 2)
            current, count = int(current_text), int(count_text)
        except ValueError:
            return

        if current >= count:  # Wait for the next step
            self.progress_bar.setRange(0, 0)
            return

        self.progress_bar.setRange(0, count)
        self.progress_bar.setValue(current)
        self.stage_label.setText(f'{prefix.rstrip(":")}  ·  {current} / {count}')

    def ask_question(self, message: str):
        answer = QMessageBox.question(self, APP_NAME, message)
        reply = 'y' if answer == QMessageBox.StandardButton.Yes else 'n'
        if self.process is not None:  # Unless it was stopped while the question was shown
            self.process.write(f'{reply}\n'.encode())

    def process_error(self, error: QProcess.ProcessError):
        if error == QProcess.ProcessError.FailedToStart and self.process is not None:
            self.log.add_message(Level.ERROR, f'Unable to start arXiv-sorter: {self.process.errorString()}', '❌')
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
        self.elapsed_timer.stop()
        self._update_elapsed()
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
        self.progress_bar.setValue(1 if outcome is Outcome.FINISHED else 0)

        summary = final_message(outcome, time.monotonic() - self.start_time, self.written, self.n_warnings)
        problems = outcome in (Outcome.ERRORS, Outcome.FAILED) or self.n_warnings > 0
        self.log.add_summary(summary, latest_log() if problems else None)
        self.stage_label.setText(f'{summary.icon} {summary.status}')
        self.statusBar().showMessage(summary.status)
        self.refresh_search_files()  # authors.txt may have been sorted
        QApplication.alert(self)  # Flash the taskbar entry (Dock icon on macOS) if the window is not active

    def changeEvent(self, event: QEvent):
        # Back from editing the search files in another program: update their counts
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.refresh_search_files()
        super().changeEvent(event)

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


def set_windows_app_id():
    """
    Give the application its own identity in the Windows taskbar. Otherwise, when run from Python, it is grouped with
    Python and shows the icon of Python instead of its own.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        pass


def start_gui() -> int:
    set_windows_app_id()  # Before any window is created
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())

    window = MainWindow()
    window.show()
    return app.exec()
