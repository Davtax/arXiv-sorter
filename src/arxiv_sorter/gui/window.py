"""
Main window of the GUI. arXiv-sorter itself runs in a separate process, whose messages are shown in the window.
"""
import codecs
import contextlib
import os
import sys
import time
from dataclasses import replace
from datetime import date, datetime
from datetime import time as time_of_day
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QDate,
    QEvent,
    QPoint,
    QPointF,
    QProcess,
    QProcessEnvironment,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPaintEvent,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractButton,
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
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionSpinBox,
    QStylePainter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from arxiv_sorter import __version__, scheduler
from arxiv_sorter.gui.date_picker import DatePicker
from arxiv_sorter.gui.icons import app_icon, run_icon, stop_icon
from arxiv_sorter.gui.log_view import COLORS, LogView, is_dark
from arxiv_sorter.gui.schedule import ScheduleDialog, describe_schedule
from arxiv_sorter.gui.search_editor import SearchFilesEditor
from arxiv_sorter.gui.search_files import SEARCH_FILES, count_terms, describe
from arxiv_sorter.gui.settings import SETTINGS_FILE, THEMES, Settings
from arxiv_sorter.gui.summary import Outcome, WrittenFile, final_message, format_duration
from arxiv_sorter.gui.theme import apply_theme
from arxiv_sorter.gui.updates import UpdateChecker, UpdateInstaller
from arxiv_sorter.log_file import latest_log, logs_dir
from arxiv_sorter.protocol import GUI_ENV_VAR, LOG_TAG, PROGRESS_TAG, QUESTION_TAG, WORKER_FLAG, WRITTEN_TAG, Level
from arxiv_sorter.run_lock import is_running
from arxiv_sorter.search_terms import Kind, Problem, Severity, check_file, check_folder
from arxiv_sorter.system import APP_NAME, base_dir, config_dir, is_frozen, kill_process_tree, max_threads
from arxiv_sorter.updater import Release, launch, remove_old_version

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # Folder that contains the arxiv_sorter package
REPOSITORY_URL = 'https://github.com/Davtax/arXiv-sorter'
WINDOWS_APP_ID = 'Davtax.arXiv-sorter.GUI'  # Identity of the application in the Windows taskbar
DATE_FORMAT = 'ddd d MMM yyyy'  # e.g. Tue 22 Sep 2026
THREADS_EXTRA_INDENT = 20  # Pixels beyond the text of "Include the first figure", to show the threads belong to it
# The macOS style draws the push buttons taller than its standard height as square bevel buttons, and every tool button
# square, so there the buttons keep their standard height and small buttons are push buttons as well
MACOS = sys.platform == 'darwin'
MIN_WINDOW_SIZE = QSize(760, 600)
SECTION_BORDER_WEIGHT = 0.25  # Color of the frame of the sections on macOS, from the background (0) to the text (1)
RUN_BUTTON_HEIGHT = 38

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


def worker_environment() -> QProcessEnvironment:
    """
    Environment of the worker process: tagged messages for the GUI, sent right away and in UTF-8.
    """
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert(GUI_ENV_VAR, '1')
    environment.insert('PYTHONUNBUFFERED', '1')
    environment.insert('PYTHONIOENCODING', 'utf-8')
    if not is_frozen():  # Make the package importable by the worker, even if it is not installed
        python_path = [str(PACKAGE_ROOT), environment.value('PYTHONPATH')]
        environment.insert('PYTHONPATH', os.pathsep.join(filter(None, python_path)))
    return environment


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


def small_button(text: str) -> QAbstractButton:
    """
    Compact button for secondary actions: a tool button, or a small rounded push button on macOS.
    """
    if not MACOS:
        tool_button = QToolButton()
        tool_button.setText(text)
        return tool_button
    button = QPushButton(text)
    button.setAttribute(Qt.WidgetAttribute.WA_MacSmallSize)
    return button


def expanding_form(parent: QWidget | None = None) -> QFormLayout:
    """
    Form whose fields take the whole width, with the labels on the left, on every platform (by default, macOS keeps
    the fields at their preferred width and aligns the labels to the right).
    """
    form = QFormLayout(parent)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return form


def style_section(group: QGroupBox):
    """
    On macOS, draw the group box like on Windows: a rounded frame with the title on its top border, and some room
    between the frame and its content. The macOS style puts the title above the frame, touching it.
    """
    if not MACOS:
        return
    palette = group.palette()
    window, text = palette.color(QPalette.ColorRole.Window), palette.color(QPalette.ColorRole.WindowText)
    border = QColor.fromRgbF(*(w + SECTION_BORDER_WEIGHT * (t - w) for w, t in zip(
        (window.redF(), window.greenF(), window.blueF()), (text.redF(), text.greenF(), text.blueF()), strict=True)))
    group.setStyleSheet(f'QGroupBox {{ border: 1px solid {border.name()}; border-radius: 6px; margin-top: 0.7em; '
                        'padding: 8px 4px 4px 4px; }'
                        'QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }')


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


class DateEdit(QDateEdit):
    """
    Date edit with a calendar popup. On macOS, the style draws a misplaced blue rectangle around it while it has the
    focus (also after a date is chosen in the calendar), so it is painted as QDateEdit does, but without the focus.
    """

    def paintEvent(self, event: QPaintEvent):
        if not MACOS or not self.calendarPopup():
            super().paintEvent(event)
            return

        spin_box = QStyleOptionSpinBox()
        self.initStyleOption(spin_box)
        combo_box = QStyleOptionComboBox()
        combo_box.initFrom(self)
        combo_box.editable = True
        combo_box.frame = spin_box.frame
        combo_box.subControls = spin_box.subControls
        combo_box.activeSubControls = spin_box.activeSubControls
        combo_box.state = spin_box.state & ~QStyle.StateFlag.State_HasFocus
        if self.isReadOnly():
            combo_box.state &= ~QStyle.StateFlag.State_Enabled
        QStylePainter(self).drawComplexControl(QStyle.ComplexControl.CC_ComboBox, combo_box)

    def open_calendar(self):
        """
        Open the calendar popup, as a click on the arrow does (QDateEdit has no function for it), so it is positioned
        and connected by Qt.
        """
        if not self.isEnabled() or not self.calendarPopup() or self.calendarWidget().isVisible():
            return
        option = QStyleOptionComboBox()
        option.initFrom(self)
        option.editable = True
        option.subControls = QStyle.SubControl.SC_All
        arrow = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                            QStyle.SubControl.SC_ComboBoxArrow, self)
        position = QPointF(arrow.center() if arrow.isValid() else QPoint(self.width() - 8, self.height() // 2))
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            event = QMouseEvent(kind, position, self.mapToGlobal(position), Qt.MouseButton.LeftButton,
                                Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress
                                else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(self, event)


class PathSelector(QWidget):
    """
    Line edit with buttons to browse for a directory and to open it in the file manager.
    """

    def __init__(self, dialog_title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.dialog_title = dialog_title

        self.line_edit = QLineEdit()
        self.line_edit.setClearButtonEnabled(True)
        self.browse_button = QPushButton('Browse…')
        self.browse_button.setToolTip('Choose the folder')
        self.browse_button.clicked.connect(self.browse)
        self.open_button = QPushButton() if MACOS else QToolButton()
        self.open_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        if MACOS:  # Only as wide as the icon, instead of the minimum width of the push buttons
            self.open_button.setFixedWidth(48)
        self.open_button.setToolTip('Open the folder in the file manager')
        self.open_button.clicked.connect(self.open_folder)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.line_edit, stretch=1)
        layout.addWidget(self.browse_button)
        layout.addWidget(self.open_button)

    def path(self) -> str:
        return self.line_edit.text().strip()

    def set_editable(self, editable: bool):
        """
        Allow changing the folder or not. It can always be opened in the file manager, e.g. during a run.
        """
        self.line_edit.setEnabled(editable)
        self.browse_button.setEnabled(editable)

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
        self.skipped_version = ''
        self.update_checker: UpdateChecker | None = None
        self.manual_update_check = False  # Asked from the menu, so the result is shown even without a new version
        self.update_installer: UpdateInstaller | None = None
        self.pending_release: Release | None = None  # Found during a run, offered once it finishes

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
        # Never smaller than the layout needs, which depends on the style (the macOS widgets are taller), or Qt squeezes
        # the widgets until they are unreadable
        self.setMinimumSize(self.minimumSizeHint().expandedTo(MIN_WINDOW_SIZE))
        self.load_settings()
        self.refresh_search_files()

    # ---------------------------------------------------------------- widgets
    def _build_folders_group(self) -> QGroupBox:
        group = QGroupBox('📁  Folders')
        style_section(group)
        form = expanding_form(group)

        self.keywords_selector = PathSelector('Select the folder with the search files')
        self.keywords_selector.setToolTip('Folder with keywords.txt, authors.txt and categories.txt (--directory)')
        self.keywords_selector.line_edit.textChanged.connect(lambda: self.search_files_timer.start())
        form.addRow('Search files:', self.keywords_selector)

        files_row = QHBoxLayout()
        self.search_file_labels: dict[str, QLabel] = {}
        self.edit_buttons: list[QAbstractButton] = []  # Disabled during a run, which reads (and sorts) the files
        for search_file in SEARCH_FILES:
            label = QLabel()
            self.search_file_labels[search_file.filename] = label
            button = small_button('Edit')
            button.setToolTip(f'Edit {search_file.filename}, checking the mistakes while you type, and preview the '
                              'submissions it would find')
            button.clicked.connect(lambda _=False, name=search_file.filename: self.edit_user_file(name))
            self.edit_buttons.append(button)
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
        style_section(group)
        grid = QGridLayout(group)

        self.auto_dates_radio = QRadioButton('Automatic')
        self.auto_dates_radio.setToolTip('Continue after the last mailing list saved in the abstracts folder')
        self.custom_dates_radio = QRadioButton('Custom range')
        self.custom_dates_radio.setToolTip('Choose the mailing lists to request (--date0 and --datef)')
        self.auto_dates_radio.setChecked(True)
        self.custom_dates_radio.toggled.connect(self._update_dates_enabled)

        today = QDate.currentDate()
        self.date_0_edit = self._date_edit(today.addDays(-7))
        self.date_0_edit.setMaximumDate(today.addDays(-1))  # The range ends on a later day
        self.date_0_edit.setToolTip('First mailing list to request (--date0)')
        self.date_f_edit = self._date_edit(today)
        self.date_f_edit.setToolTip('Submissions are requested until the arXiv deadline (14:00 ET) of this day, so its '
                                    'own mailing list is not included (--datef)')

        for edit in (self.date_0_edit, self.date_f_edit):  # Both calendars shade the range between the two dates
            edit.dateChanged.connect(self._update_date_range)
        self._update_date_range()
        # As in the date pickers of booking websites: once the first day is chosen, the calendar of the last one opens,
        # and hovering a day previews the range
        start_calendar, end_calendar = self.date_0_edit.calendarWidget(), self.date_f_edit.calendarWidget()
        if isinstance(start_calendar, DatePicker) and isinstance(end_calendar, DatePicker):
            start_calendar.chooses, end_calendar.chooses = 'start', 'end'
            start_calendar.clicked.connect(lambda _date: QTimer.singleShot(0, self.date_f_edit.open_calendar))

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
    def _date_edit(value: QDate) -> DateEdit:
        edit = DateEdit(value)
        edit.setCalendarPopup(True)
        edit.setCalendarWidget(DatePicker())
        edit.setDisplayFormat(DATE_FORMAT)
        edit.setMaximumDate(QDate.currentDate())
        if MACOS:
            # The style draws the frame of a combo box, and the text field inside with its own background, as a darker
            # box. A style sheet (unlike a palette) survives the style being created again when the theme changes, but
            # it makes the text field shorter, so the height of the date edit is kept
            edit.setMinimumHeight(edit.sizeHint().height())
            edit.lineEdit().setStyleSheet('background: transparent; border: none')
        return edit

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox('⚙️  Options')
        style_section(group)
        box = QVBoxLayout(group)

        self.images_check = QCheckBox('Include the first figure of each new submission')
        self.images_check.setToolTip('Download the PDFs and extract their first figure (Java is downloaded the first '
                                     'time if it is not installed). Slower, and arXiv may limit the downloads (untick '
                                     'for --image)')
        self.final_date_check = QCheckBox('Add a timestamp at the end of the Markdown file')
        self.final_date_check.setToolTip('Untick for --final')
        self.separate_check = QCheckBox('Create a separate file for each submission')
        self.separate_check.setToolTip('A folder per mailing list, with a Markdown file per submission (--separate)')
        self.sort_authors_check = QCheckBox('Sort authors.txt and remove its blank lines')
        self.sort_authors_check.setToolTip('Untick for --modify')
        self.verbose_check = QCheckBox('Show detailed messages')
        self.verbose_check.setToolTip('Useful to understand a problem (--verbose)')

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, max_threads())
        self.threads_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.threads_spin.setMinimumWidth(self.threads_spin.fontMetrics().horizontalAdvance('0000') + 30)  # Arrows
        self.threads_spin.setToolTip(f'Threads to detect and extract the figures, up to {max_threads()} (CPUs of this '
                                     'system). More threads are faster, but use more memory (--threads)')
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
        for check in (self.final_date_check, self.separate_check, self.sort_authors_check,
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
        if not MACOS:
            self.run_button.setMinimumHeight(RUN_BUTTON_HEIGHT)
        self.run_button.setMinimumWidth(110)
        font = self.run_button.font()
        font.setBold(True)
        self.run_button.setFont(font)
        self.run_button.clicked.connect(self.start)

        self.stop_button = QPushButton('  Stop')
        self.stop_button.setIcon(stop_icon())
        self.stop_button.setToolTip('Stop arXiv-sorter. The mailing lists already saved are kept')
        if not MACOS:
            self.stop_button.setMinimumHeight(RUN_BUTTON_HEIGHT)
        self.stop_button.setMinimumWidth(110)
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
        style_section(group)
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

        copy_button = small_button('Copy')
        copy_button.setToolTip('Copy the messages to the clipboard, e.g. to report a problem')
        copy_button.clicked.connect(self.copy_messages)
        save_button = small_button('Save…')
        save_button.setToolTip('Save the messages in a text file')
        save_button.clicked.connect(self.save_messages)
        clear_button = small_button('Clear')
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
        self._add_action(file_menu, 'Run every day…', self.edit_schedule)
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
        self._add_action(help_menu, 'Check for updates…', lambda: self.check_for_updates(manual=True)).setMenuRole(
            QAction.MenuRole.ApplicationSpecificRole)
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
        # Same choices as View → Theme, easier to find
        self.theme_button: QPushButton | QToolButton
        if MACOS:  # The tool button draws its menu arrow over the text there
            self.theme_button = QPushButton()
            self.theme_button.setAttribute(Qt.WidgetAttribute.WA_MacSmallSize)
            self.theme_button.setFlat(True)
        else:
            theme_button = QToolButton()
            theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            theme_button.setAutoRaise(True)
            self.theme_button = theme_button
        self.theme_button.setMenu(self.theme_menu)
        self.theme_button.setToolTip('Light or dark theme')

        # Same as File → Run every day…, showing the time of the daily run
        self.schedule_button: QAbstractButton
        if MACOS:
            self.schedule_button = QPushButton()
            self.schedule_button.setAttribute(Qt.WidgetAttribute.WA_MacSmallSize)
            self.schedule_button.setFlat(True)
        else:
            schedule_button = QToolButton()
            schedule_button.setAutoRaise(True)
            self.schedule_button = schedule_button
        self.schedule_button.setToolTip('Run arXiv-sorter every day in the background, change the time, or stop it')
        self.schedule_button.clicked.connect(self.edit_schedule)
        with contextlib.suppress(scheduler.SchedulerError):  # Shown as it is, and can be scheduled from the dialog
            scheduler.follow_program()
        self.refresh_schedule()

        self.statusBar().addPermanentWidget(self.elapsed_label)
        self.statusBar().addPermanentWidget(self.schedule_button)
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
        for group in self.findChildren(QGroupBox):  # The color of their frame depends on the theme
            style_section(group)
        self.refresh_search_files()  # Their warning colors depend on the theme
        if save:
            self.save_settings()

    def _update_threads_enabled(self):
        enabled = self.images_check.isChecked() and self.run_button.isEnabled()
        self.threads_spin.setEnabled(enabled)
        self.threads_label.setEnabled(enabled)

    def _update_date_range(self, *_):
        # The last day comes after the first one (a later first day moves it): the days before cannot be chosen
        self.date_f_edit.setMinimumDate(self.date_0_edit.date().addDays(1))
        start, end = self.date_0_edit.date(), self.date_f_edit.date()
        for edit in (self.date_0_edit, self.date_f_edit):
            calendar = edit.calendarWidget()
            if isinstance(calendar, DatePicker):
                calendar.set_range(start, end)

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
                        skipped_version=self.skipped_version,
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
        self.verbose_check.setChecked(settings.verbose)
        self.custom_dates_radio.setChecked(settings.custom_dates)
        self.auto_dates_radio.setChecked(not settings.custom_dates)

        for edit, value in ((self.date_0_edit, settings.date_0), (self.date_f_edit, settings.date_f)):
            saved_date = QDate.fromString(value, Qt.DateFormat.ISODate)
            if saved_date.isValid():
                edit.setDate(min(saved_date, QDate.currentDate()))

        self.skipped_version = settings.skipped_version
        self.set_theme(settings.theme, save=False)
        # After the theme: creating the style again resets the size of a window that is not shown yet (macOS)
        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(settings.window_geometry.encode('ascii')))
        else:
            self.resize(1000, 780)

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
        Open the editor of the search files on the given file (and line). Not during a run, which reads the files and
        may sort authors.txt.
        """
        if self.process is not None:
            return
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
            '<p>Settings, pdffigures2 and Java are kept in<br>'
            f'<a href="{QUrl.fromLocalFile(str(config_dir())).toString()}">'
            f'{config_dir()}</a></p>'
            '<p>MIT License</p>')

    # --------------------------------------------------------------- schedule
    def refresh_schedule(self) -> time_of_day | None:
        """
        Show the time of the daily run, as kept by the operating system.
        """
        try:
            at = scheduler.scheduled_time()
        except scheduler.SchedulerError:
            at = None
        self.schedule_button.setText(f'⏰ {describe_schedule(at)}')
        return at

    def edit_schedule(self):
        """
        Run arXiv-sorter every day at the time chosen by the user, change the time, or stop it. The daily run uses the
        settings saved in the settings file, so they are saved first.
        """
        current = self.refresh_schedule()
        dialog = ScheduleDialog(current, self)
        if not dialog.exec():
            return
        chosen = dialog.chosen_time()

        settings = self.current_settings()
        if chosen is not None:
            error = self.validate(replace(settings, custom_dates=False))
            if error is not None:
                QMessageBox.information(self, APP_NAME, error)
                return
        self.save_settings()

        try:
            if chosen is not None:
                scheduler.schedule(chosen)
            elif current is not None:
                scheduler.unschedule()
        except scheduler.SchedulerError as error:
            QMessageBox.warning(self, APP_NAME, f'Unable to change the daily run: {error}')
        at = self.refresh_schedule()
        self.statusBar().showMessage(f'Daily run: {describe_schedule(at).lower()}', 5000)

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
        if is_running():
            QMessageBox.information(self, APP_NAME, 'arXiv-sorter is already running, e.g. the daily run in the '
                                    'background, or from a terminal. Try again when it finishes.')
            return
        self.save_settings()

        program, arguments = worker_command()
        arguments += settings.to_cli_args()

        self.process = QProcess(self)
        self.process.setProgram(program)
        self.process.setArguments(arguments)
        self.process.setProcessEnvironment(worker_environment())
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
        for selector in (self.keywords_selector, self.abstracts_selector):
            selector.set_editable(not running)
        for widget in (self.auto_dates_radio, self.custom_dates_radio, self.images_check, self.final_date_check,
                       self.separate_check, self.sort_authors_check, self.verbose_check, *self.edit_buttons):
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

        if self.pending_release is not None:
            release, self.pending_release = self.pending_release, None
            self.offer_update(release)

    # ---------------------------------------------------------------- updates
    def check_for_updates(self, manual: bool = False):
        """
        Look for a new version in GitHub, in the background. When the window opens (manual=False), nothing is shown
        unless there is a new version that was not skipped; when asked from the menu, the result is always shown.
        """
        if self.update_checker is not None or self.update_installer is not None:
            return
        if not is_frozen():
            if manual:
                QMessageBox.information(self, APP_NAME, f'{APP_NAME} v{__version__} runs from its Python sources, so '
                                        'it is updated from the repository instead.')
            return

        self.statusBar().showMessage('Checking for updates …', 5000)
        self.update_checker = UpdateChecker(self)
        self.manual_update_check = manual
        self.update_checker.checked.connect(self.update_checked)  # Called in the thread of the window
        self.update_checker.start()

    def update_checked(self, release: Release | None, error: str):
        self.update_checker = None
        manual = self.manual_update_check
        if release is None:
            if manual and error:
                QMessageBox.warning(self, APP_NAME, error)
            elif manual:
                QMessageBox.information(self, APP_NAME, f'{APP_NAME} v{__version__} is the latest version.')
            return

        if not manual and release.version == self.skipped_version:
            return
        if self.process is not None:  # Not in the middle of a run
            self.pending_release = release
            return
        self.offer_update(release)

    def offer_update(self, release: Release):
        """
        Ask whether to upgrade to the release now, or to skip it (it is not offered again when the window opens).
        """
        box = QMessageBox(QMessageBox.Icon.Information, APP_NAME,
                          f'<b>{APP_NAME} {release.version} is available</b> (you have v{__version__}).', parent=self)
        page = f' <a href="{release.page}">What is new?</a>' if release.page else ''
        box.setInformativeText(f'Upgrade downloads it, replaces this version and opens it again. Your settings and '
                               f'search files are kept.{page}')
        box.setTextFormat(Qt.TextFormat.RichText)
        if release.notes:
            box.setDetailedText(release.notes)
        upgrade_button = box.addButton('Upgrade', QMessageBox.ButtonRole.AcceptRole)
        box.addButton('Skip', QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(upgrade_button)
        box.exec()

        if box.clickedButton() is upgrade_button:
            self.upgrade(release)
        else:
            self.skipped_version = release.version
            self.save_settings()
            self.statusBar().showMessage(f'{release.version} skipped. Help → Check for updates… to install it later',
                                         8000)

    def upgrade(self, release: Release):
        """
        Download and install the release, with a progress dialog, then restart with the new version.
        """
        dialog = QProgressDialog(f'Downloading {APP_NAME} {release.version} …', 'Cancel', 0, 0, self)
        dialog.setWindowTitle(APP_NAME)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)

        def show_progress(received: int, total: int):
            if total and received >= total:
                dialog.setLabelText(f'Installing {APP_NAME} {release.version} …')
                dialog.setRange(0, 0)
                dialog.setCancelButton(None)  # Too late to cancel: the program is being replaced
            elif total:
                dialog.setRange(0, total)
                dialog.setValue(received)

        installer = UpdateInstaller(release, self)
        installer.progress.connect(show_progress)
        installer.installed.connect(self.restart_updated)
        installer.failed.connect(lambda error: self.update_failed(release, error))
        installer.finished.connect(dialog.deleteLater)
        installer.finished.connect(installer.deleteLater)
        dialog.canceled.connect(installer.cancel)
        self.update_installer = installer
        self.set_running(True)  # No run while the program is replaced
        self.stop_button.setEnabled(False)
        dialog.show()
        installer.start()

    def update_failed(self, release: Release, error: str):
        self.update_installer = None
        self.set_running(False)
        if not error:
            self.statusBar().showMessage('Update cancelled', 5000)
            return

        box = QMessageBox(QMessageBox.Icon.Warning, APP_NAME, f'Unable to update {APP_NAME} to {release.version}.',
                          parent=self)
        box.setInformativeText(error)
        download_button = box.addButton('Open the download page', QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is download_button:
            open_url(release.page or f'{REPOSITORY_URL}/releases/latest')

    def restart_updated(self, program: Path):
        """
        The new version replaced this one: open it, and close this window.
        """
        self.update_installer = None
        self.set_running(False)
        self.save_settings()  # Read by the new version when it opens
        try:
            launch(program)
        except OSError as error:
            QMessageBox.warning(self, APP_NAME, f'{APP_NAME} was updated, but the new version could not be opened '
                                f'({error}). Open it again from {program}.')
        self.close()
        QApplication.quit()

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
        if self.update_installer is not None:  # Stops the download; the replacement itself only takes a moment
            self.update_installer.cancel()
            self.update_installer.wait()

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

    if is_frozen():
        remove_old_version()  # Left by the last update

    window = MainWindow()
    window.show()
    window.check_for_updates()
    return app.exec()
