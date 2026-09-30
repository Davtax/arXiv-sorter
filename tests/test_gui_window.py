"""
Logic of the main window and of the editor of the search files, with pytest-qt.
"""
import json
import os
import sys
import time
from datetime import time as time_of_day
from pathlib import Path

import pytest

# Linux CI runners have no display. Elsewhere the real platform is used, so the tests run with its native style
if sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QtCore = pytest.importorskip('PySide6.QtCore')
pytest.importorskip('pytestqt')

from arxorter import run_lock, scheduler  # noqa: E402
from arxorter.gui import background  # noqa: E402
from arxorter.gui import updates as updates_module  # noqa: E402
from arxorter.gui import window as window_module  # noqa: E402
from arxorter.gui.search_editor import SearchFilesEditor, abstract_excerpt, highlighted_html  # noqa: E402
from arxorter.gui.summary import Outcome, WrittenFile  # noqa: E402
from arxorter.protocol import BUSY_EXIT_CODE, LOG_TAG, PROGRESS_TAG, WRITTEN_TAG  # noqa: E402
from arxorter.search_terms import Kind  # noqa: E402
from arxorter.sorting import AbstractEnclosure  # noqa: E402
from arxorter.updater import Release, UpdateError  # noqa: E402


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """
    Modal dialogs would wait for a click forever. Questions are answered with Discard/No, e.g. when the widgets are
    closed at the end of a test with unsaved changes or a run in progress.
    """
    answers = []
    message_box = window_module.QMessageBox

    def answer(*args, **kwargs):
        answers.append(args)
        return message_box.StandardButton.Discard

    for name in ('question', 'warning', 'information'):
        monkeypatch.setattr(message_box, name, answer)
    monkeypatch.setattr(message_box, 'exec', lambda box: answers.append(box.informativeText()))
    return answers


@pytest.fixture
def searches(tmp_path):
    folder = tmp_path / 'searches'
    folder.mkdir()
    (folder / 'keywords.txt').write_text('spin qubit\nquantum dot\n', encoding='utf-8')
    (folder / 'authors.txt').write_text('Loss\n', encoding='utf-8')
    (folder / 'categories.txt').write_text('cond-mat\n', encoding='utf-8')
    return folder


@pytest.fixture
def daily_run(monkeypatch):
    """The scheduler of the operating system, replaced by a variable: the time of the daily run, or None."""
    state = {'time': None}
    monkeypatch.setattr(scheduler, 'scheduled_time', lambda: state['time'])
    monkeypatch.setattr(scheduler, 'schedule', lambda at: state.update(time=at))
    monkeypatch.setattr(scheduler, 'unschedule', lambda: state.update(time=None))
    return state


@pytest.fixture
def make_window(qtbot, tmp_path, monkeypatch, searches, daily_run):
    """Windows with their settings in a temporary file, never in the real configuration folder."""
    monkeypatch.setattr(window_module, 'settings_path', lambda: tmp_path / 'settings.json')

    def make():
        win = window_module.MainWindow()
        qtbot.addWidget(win)
        win.keywords_selector.set_path(str(searches))
        win.abstracts_selector.set_path(str(tmp_path / 'abstracts'))
        win.refresh_search_files()
        return win

    yield make
    window_module.apply_theme(window_module.QApplication.instance(), 'system')


@pytest.fixture
def win(make_window):
    return make_window()


def finish(win, exit_code=0, exit_status=QtCore.QProcess.ExitStatus.NormalExit):
    """Simulate the end of the arXorter process."""
    win.process = QtCore.QProcess(win)
    win.set_running(True)
    win.process_finished(exit_code, exit_status)


class TestRunning:
    def test_search_files_cannot_be_edited_during_a_run(self, win, monkeypatch):
        opened = []
        monkeypatch.setattr(window_module.SearchFilesEditor, 'exec', lambda editor: opened.append(editor))

        win.process = QtCore.QProcess(win)
        win.set_running(True)
        assert not any(button.isEnabled() for button in win.edit_buttons)
        win.edit_user_file('keywords.txt')
        assert not opened

        win.process_finished(0, QtCore.QProcess.ExitStatus.NormalExit)
        assert all(button.isEnabled() for button in win.edit_buttons)
        win.edit_user_file('keywords.txt')
        assert len(opened) == 1


    def test_folders_can_be_opened_but_not_changed_during_a_run(self, win):
        win.process = QtCore.QProcess(win)
        win.set_running(True)
        for selector in (win.keywords_selector, win.abstracts_selector):
            assert selector.open_button.isEnabled()
            assert not selector.line_edit.isEnabled()
            assert not selector.browse_button.isEnabled()

        win.process_finished(0, QtCore.QProcess.ExitStatus.NormalExit)
        assert win.abstracts_selector.line_edit.isEnabled()
        assert win.abstracts_selector.browse_button.isEnabled()


class TestSchedule:
    @pytest.fixture
    def choose(self, monkeypatch):
        """Answer the dialog of the daily run with the given time (None to remove it), or cancel it."""
        answer = {}

        def exec_dialog(dialog):
            if answer.get('cancel'):
                return False
            dialog.enabled_check.setChecked(answer['time'] is not None)
            if answer['time'] is not None:
                dialog.time_edit.setTime(QtCore.QTime(answer['time'].hour, answer['time'].minute))
            return True

        monkeypatch.setattr(window_module.ScheduleDialog, 'exec', exec_dialog)
        return answer

    def test_the_daily_run_is_created_changed_and_removed(self, win, choose, daily_run, tmp_path):
        assert win.schedule_button.text().endswith('Not scheduled')

        choose['time'] = time_of_day(8, 30)
        win.edit_schedule()
        assert daily_run['time'] == time_of_day(8, 30)
        assert win.schedule_button.text().endswith('Daily at 08:30')
        saved = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
        assert saved['keywords_dir'] == win.keywords_selector.path()  # The daily run uses the saved settings

        choose['time'] = time_of_day(18, 0)
        win.edit_schedule()
        assert win.schedule_button.text().endswith('Daily at 18:00')

        choose['cancel'] = True
        win.edit_schedule()
        assert daily_run['time'] == time_of_day(18, 0)

        choose.update(cancel=False, time=None)
        win.edit_schedule()
        assert daily_run['time'] is None
        assert win.schedule_button.text().endswith('Not scheduled')

    def test_the_dialog_shows_the_current_time(self, qtbot):
        dialog = window_module.ScheduleDialog(time_of_day(7, 15))
        qtbot.addWidget(dialog)
        assert dialog.enabled_check.isChecked()
        assert dialog.chosen_time() == time_of_day(7, 15)
        dialog.enabled_check.setChecked(False)
        assert dialog.chosen_time() is None
        assert not dialog.time_edit.isEnabled()

    def test_errors_of_the_scheduler_are_shown(self, win, choose, monkeypatch, no_modal_dialogs):
        def fail(at):
            raise scheduler.SchedulerError('schtasks failed: access denied')

        monkeypatch.setattr(scheduler, 'schedule', fail)
        choose['time'] = time_of_day(8, 0)
        win.edit_schedule()
        assert any('access denied' in str(answer) for answer in no_modal_dialogs)
        assert win.schedule_button.text().endswith('Not scheduled')


class TestBackground:
    FILE = WrittenFile(Path('abstracts/2026-09-29.md'), 120, 7)

    def test_notification_of_new_mailing_lists(self):
        title, text = background.notification_text(Outcome.FINISHED, [self.FILE, self.FILE])
        assert '2 mailing lists sorted' in title
        assert text.startswith('14 submissions new or matching')

    def test_notification_without_new_mailing_lists(self):
        title, _ = background.notification_text(Outcome.FINISHED, [])
        assert 'nothing new' in title

    def test_notification_of_errors(self):
        title, text = background.notification_text(Outcome.ERRORS, [self.FILE], 'No connection')
        assert 'errors' in title
        assert text.startswith('No connection\n1 mailing list sorted.')
        assert 'log' in text

    def test_the_output_of_the_worker_is_collected(self, qtbot, monkeypatch):
        notifications = []
        monkeypatch.setattr(background.BackgroundRun, 'notify', lambda run, *message: notifications.append(message))
        run = background.BackgroundRun(window_module.Settings(keywords_dir='k', abstracts_dir='a'))
        run.handle_line(f'{WRITTEN_TAG}120\t7\t{self.FILE.path}')
        run.handle_line(f'{LOG_TAG}error\t❌\tNo connection')
        run.handle_line(f'{LOG_TAG}error\t❌\tA second error')
        run.process_finished(1, QtCore.QProcess.ExitStatus.NormalExit)

        assert run.written == [self.FILE]
        assert run.first_error == 'No connection'
        assert 'errors' in notifications[0][0]

    def test_the_run_is_skipped_while_another_one_runs(self, qtbot, monkeypatch):
        notifications = []
        monkeypatch.setattr(background.BackgroundRun, 'notify', lambda run, *message: notifications.append(message))
        run = background.BackgroundRun(window_module.Settings(keywords_dir='k', abstracts_dir='a'))
        run.handle_line(f'{LOG_TAG}error\t⏳\tarXorter is already running')
        run.process_finished(BUSY_EXIT_CODE, QtCore.QProcess.ExitStatus.NormalExit)

        assert notifications[0][0].endswith('daily run skipped')


class TestOutput:
    def test_messages_are_shown_and_counted(self, win):
        win.handle_line(f'{LOG_TAG}step\t📅\tMailing list of Tue 22 Sep 2026')
        win.handle_line(f'{LOG_TAG}warning\t⚠️\tCareful')
        win.handle_line(f'{LOG_TAG}warning\t⚠️\tCareful again')
        win.handle_line('Traceback (most recent call last):')

        text = win.log.toPlainText()
        assert 'Mailing list of Tue 22 Sep 2026' in text and 'Traceback' in text
        assert win.n_warnings == 2 and not win.errors_found
        assert win.stage_label.text() == '📅 Mailing list of Tue 22 Sep 2026'

    def test_errors_are_detected(self, win):
        win.handle_line(f'{LOG_TAG}error\t❌\tBroken')

        assert win.errors_found

    def test_progress(self, win):
        win.handle_line(f'{PROGRESS_TAG}3\t10\tDownloading PDFs')

        assert (win.progress_bar.value(), win.progress_bar.maximum()) == (3, 10)
        assert win.stage_label.text() == 'Downloading PDFs  ·  3 / 10'

    def test_written_files_enable_opening_the_latest(self, win, tmp_path):
        assert not win.open_latest_button.isEnabled()

        win.handle_line(f'{WRITTEN_TAG}103\t101\t{tmp_path / "2026-09-22.md"}')

        assert win.written[0].n_entries == 103
        assert win.open_latest_button.isEnabled()

    def test_lines_rewritten_with_carriage_returns(self, win):
        win.handle_line('Waiting 3 s\rWaiting 2 s\r')

        assert 'Waiting 2 s' in win.log.toPlainText() and 'Waiting 3 s' not in win.log.toPlainText()


class TestEndOfRun:
    @pytest.mark.parametrize(('prepare', 'exit_code', 'exit_status', 'status'), [
        (None, 0, QtCore.QProcess.ExitStatus.NormalExit, 'Done: nothing new to sort'),
        ('error', 0, QtCore.QProcess.ExitStatus.NormalExit, 'Finished with errors'),
        (None, 1, QtCore.QProcess.ExitStatus.NormalExit, 'Finished with errors'),
        (None, 0, QtCore.QProcess.ExitStatus.CrashExit, 'Failed'),
        ('stop', 0, QtCore.QProcess.ExitStatus.CrashExit, 'Stopped'),
    ])
    def test_outcomes(self, win, prepare, exit_code, exit_status, status):
        if prepare == 'error':
            win.handle_line(f'{LOG_TAG}error\t❌\tBroken')
        elif prepare == 'stop':
            win.stop_requested = True

        finish(win, exit_code, exit_status)

        assert win.statusBar().currentMessage() == status
        assert win.run_button.isEnabled() and not win.stop_button.isEnabled()
        assert win.process is None

    def test_summary_lists_the_files(self, win, tmp_path):
        win.handle_line(f'{WRITTEN_TAG}103\t101\t{tmp_path / "2026-09-22.md"}')

        finish(win)

        assert 'Done in' in win.log.toPlainText() and '2026-09-22.md' in win.log.toPlainText()
        assert win.progress_bar.value() == win.progress_bar.maximum()

    def test_log_file_linked_when_something_went_wrong(self, win, tmp_path):
        log = tmp_path / 'logs' / '2026-09-29 10-00-00.log'
        log.parent.mkdir()
        log.write_text('log', encoding='utf-8')
        win.handle_line(f'{LOG_TAG}error\t❌\tBroken')

        finish(win)

        assert 'All the details are in the log file 2026-09-29 10-00-00.log' in win.log.toPlainText()


class TestControls:
    def test_dates_only_for_a_custom_range(self, win):
        win.auto_dates_radio.setChecked(True)
        widgets = (win.date_0_label, win.date_0_edit, win.date_f_label, win.date_f_edit)
        assert not any(widget.isEnabled() for widget in widgets)

        win.custom_dates_radio.setChecked(True)
        assert all(widget.isEnabled() for widget in widgets)

        win.process = QtCore.QProcess(win)  # During a run
        win.set_running(True)
        assert not any(widget.isEnabled() for widget in widgets)
        win.process = None

    def test_threads_only_with_figures(self, win):
        win.images_check.setChecked(False)
        assert not win.threads_spin.isEnabled()

        win.images_check.setChecked(True)
        assert win.threads_spin.isEnabled()

    def test_options_are_translated_to_the_command_line(self, win):
        win.images_check.setChecked(True)
        win.threads_spin.setValue(1)
        win.verbose_check.setChecked(True)
        win.separate_check.setChecked(True)

        arguments = win.current_settings().to_cli_args()

        assert {'--verbose', '--separate', '--threads', '--exit'} <= set(arguments)


class TestSearchFiles:
    def test_counts(self, win):
        assert win.search_file_labels['keywords.txt'].text() == '🔑 2 keywords'
        assert win.search_file_labels['authors.txt'].text() == '👤 1 author'

    def test_mistakes_are_flagged(self, win, searches):
        (searches / 'keywords.txt').write_text('spin[ qubit\n', encoding='utf-8')

        win.refresh_search_files()

        label = win.search_file_labels['keywords.txt']
        assert label.text().startswith('❌')
        assert 'keywords.txt, line 1: invalid regular expression' in label.toolTip()

    def test_run_is_not_started_with_mistakes(self, win, searches, no_modal_dialogs):
        (searches / 'keywords.txt').write_text('spin[ qubit\n', encoding='utf-8')

        win.start()

        assert win.process is None
        assert 'keywords.txt, line 1' in no_modal_dialogs[0]

    def test_run_is_not_started_while_another_one_runs(self, win, no_modal_dialogs):
        with run_lock.RunLock() as lock:  # e.g. the daily run, in the background
            assert lock.acquire()
            win.start()

        assert win.process is None
        assert 'already running' in str(no_modal_dialogs[0])


class TestTheme:
    def test_remembered_for_the_next_time(self, make_window, tmp_path):
        first = make_window()
        first.set_theme('dark')

        assert json.loads((tmp_path / 'settings.json').read_text())['theme'] == 'dark'
        second = make_window()
        assert second.theme == 'dark'
        assert [action.isChecked() for action in second.theme_actions.actions()] == [False, False, True]



RELEASE = Release(version='v9.9.9', url='https://example.org/arXorter-GUI-Windows.zip',
                  asset='arXorter-GUI-Windows.zip', page='https://example.org/v9.9.9', notes='New features')


@pytest.fixture
def click(monkeypatch):
    """Answer the next message boxes built by the window by clicking the button with the given text."""
    def choose(text):
        monkeypatch.setattr(window_module.QMessageBox, 'clickedButton',
                            lambda box: next(button for button in box.buttons() if button.text() == text))
    return choose


class TestUpdates:
    def test_offered_when_found(self, win, no_modal_dialogs, monkeypatch, click):
        upgraded = []
        monkeypatch.setattr(win, 'upgrade', upgraded.append)
        click('Upgrade')

        win.update_checked(RELEASE, '')

        assert 'Upgrade downloads it' in no_modal_dialogs[-1]
        assert upgraded == [RELEASE]

    def test_skipped_version_is_remembered(self, win, make_window, tmp_path, no_modal_dialogs):
        win.update_checked(RELEASE, '')  # The message box closes without a click, like Skip

        assert json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))['skipped_version'] == 'v9.9.9'
        n_dialogs = len(no_modal_dialogs)
        new_window = make_window()
        new_window.update_checked(RELEASE, '')
        assert len(no_modal_dialogs) == n_dialogs  # Not offered again when the window opens

        new_window.manual_update_check = True
        new_window.update_checked(RELEASE, '')
        assert len(no_modal_dialogs) == n_dialogs + 1  # But offered when asked from the menu

    def test_offered_after_the_run(self, win, no_modal_dialogs):
        win.process = QtCore.QProcess(win)
        win.update_checked(RELEASE, '')
        assert win.pending_release == RELEASE and not no_modal_dialogs

        win.set_running(True)
        win.process_finished(0, QtCore.QProcess.ExitStatus.NormalExit)

        assert win.pending_release is None
        assert 'Upgrade downloads it' in no_modal_dialogs[-1]

    @pytest.mark.parametrize(('error', 'expected'), [('', 'is the latest version'), ('No internet', 'No internet')])
    def test_manual_check_without_update(self, win, no_modal_dialogs, error, expected):
        win.manual_update_check = True
        win.update_checked(None, error)
        assert expected in str(no_modal_dialogs[-1])

    def test_nothing_shown_at_startup_without_update(self, win, no_modal_dialogs):
        win.update_checked(None, 'No internet')
        assert not no_modal_dialogs

    def test_not_checked_from_the_python_sources(self, win, monkeypatch, no_modal_dialogs):
        monkeypatch.setattr(window_module, 'is_frozen', lambda: False)
        win.check_for_updates()
        assert win.update_checker is None and not no_modal_dialogs

        win.check_for_updates(manual=True)
        assert 'Python sources' in str(no_modal_dialogs[-1])

    def test_checked_in_the_background(self, win, qtbot, monkeypatch):
        monkeypatch.setattr(window_module, 'is_frozen', lambda: True)
        monkeypatch.setattr(updates_module, 'latest_release', lambda: {'tag_name': 'v0.0.1', 'assets': []})
        offered = []
        monkeypatch.setattr(win, 'offer_update', offered.append)

        win.check_for_updates()
        # The thread may answer before a waitSignal would connect, so the result handled by the window is awaited
        qtbot.waitUntil(lambda: win.update_checker is None, timeout=5000)

        assert win.update_checker is None and not offered  # Older than this version

    def test_installed_then_restarted(self, win, qtbot, monkeypatch, tmp_path):
        program = tmp_path / 'arXorter-GUI.exe'
        monkeypatch.setattr(updates_module, 'install_update', lambda release, progress: program)
        launched, quit_calls = [], []
        monkeypatch.setattr(window_module, 'launch', launched.append)
        monkeypatch.setattr(window_module.QApplication, 'quit', lambda: quit_calls.append(True))

        win.upgrade(RELEASE)
        assert not win.run_button.isEnabled()
        qtbot.waitUntil(lambda: win.update_installer is None, timeout=5000)

        assert launched == [program] and quit_calls
        assert (tmp_path / 'settings.json').is_file()

    def test_failed_install(self, win, qtbot, monkeypatch, no_modal_dialogs):
        def fail(release, progress):
            raise UpdateError('Unable to write in the folder')

        monkeypatch.setattr(updates_module, 'install_update', fail)

        win.upgrade(RELEASE)
        qtbot.waitUntil(lambda: win.update_installer is None, timeout=5000)

        assert 'Unable to write in the folder' in no_modal_dialogs[-1]
        assert win.run_button.isEnabled()

    def test_cancelled_install(self, win, qtbot, monkeypatch, no_modal_dialogs):
        def cancelled(release, progress):
            while True:  # Until the progress callback raises UpdateCancelled
                progress(10, 100)
                time.sleep(0.01)

        monkeypatch.setattr(updates_module, 'install_update', cancelled)

        win.upgrade(RELEASE)
        win.update_installer.cancel()
        qtbot.waitUntil(lambda: win.update_installer is None, timeout=5000)

        assert win.statusBar().currentMessage() == 'Update cancelled'
        assert not no_modal_dialogs

class TestSearchFilesEditor:
    @pytest.fixture
    def editor(self, qtbot, searches):
        editor = SearchFilesEditor(searches)
        qtbot.addWidget(editor)
        return editor

    def test_mistakes_marked_while_typing(self, editor):
        editor.file_tabs[Kind.KEYWORDS].editor.setPlainText('quantum dot\nspin[ qubit\n')
        editor.refresh()

        assert editor.tabs.tabText(0) == '❌ keywords.txt •'
        assert 'Line 2' in editor.file_tabs[Kind.KEYWORDS].problems_label.text()
        assert len(editor.file_tabs[Kind.KEYWORDS].editor.extraSelections()) == 1

    def test_save_writes_the_modified_files(self, editor, searches):
        editor.file_tabs[Kind.AUTHORS].editor.setPlainText('Loss\nBurkard')

        assert editor.save()

        assert (searches / 'authors.txt').read_text(encoding='utf-8') == 'Loss\nBurkard\n'
        assert not editor.is_modified()
        assert editor.tabs.tabText(1) == 'authors.txt'

    def test_open_file_at_a_line(self, editor):
        editor.open_file('keywords.txt', 2)

        tab = editor.file_tabs[Kind.KEYWORDS]
        assert editor.tabs.currentWidget() is tab
        assert tab.editor.textCursor().blockNumber() == 1

    def test_preview_uses_the_unsaved_terms(self, editor, make_entry):
        from arxorter.formatting import fix_entry
        from arxorter.preview import LatestSubmissions

        entries = [make_entry(arxiv_id='1v1', title='Germanium holes'), make_entry(arxiv_id='2v1', title='Other')]
        for entry in entries:
            fix_entry(entry)
        editor.latest = LatestSubmissions(QtCore.QDateTime.currentDateTime().toPython(), entries)

        editor.file_tabs[Kind.KEYWORDS].editor.setPlainText('germanium')
        editor.refresh()

        assert '<b>1</b> of the 2 submissions' in editor.preview_status.text()
        assert 'Germanium' in editor.preview.toPlainText()


class TestOwnText:
    @pytest.fixture
    def editor(self, qtbot, searches):
        editor = SearchFilesEditor(searches)
        qtbot.addWidget(editor)
        return editor

    def test_hint_while_empty(self, editor):
        assert 'appears here while you type' in editor.own_result.toPlainText()

    def test_found_with_the_matches(self, editor):
        editor.own_title.setText('A spin qubit in silicon')
        editor.own_authors.setText('Daniel Loss, Alice Smith')
        editor.update_preview()

        text = editor.own_result.toPlainText()
        assert '✅ It would be found (matches in the title, authors)' in text
        assert 'Title: A spin qubit in silicon' in text
        assert 'color:orange' in editor.own_result.toHtml() or '#ffa500' in editor.own_result.toHtml()

    def test_not_found(self, editor):
        editor.own_abstract.setPlainText('Nothing related at all.')
        editor.update_preview()

        assert '❌ It would not be found' in editor.own_result.toPlainText()

    def test_uses_the_unsaved_terms(self, editor):
        editor.own_title.setText('Majorana modes in nanowires')
        editor.update_preview()
        assert '❌' in editor.own_result.toPlainText()

        editor.file_tabs[Kind.KEYWORDS].editor.setPlainText('majorana')
        editor.refresh()
        assert '✅' in editor.own_result.toPlainText()

    def test_text_with_html_characters(self, editor):
        editor.own_title.setText('Spin qubits with T<sub>2</sub> > 1 ms & <b>more</b>')
        editor.update_preview()

        assert 'Title: Spin qubits with T<sub>2</sub> > 1 ms & <b>more</b>' in editor.own_result.toPlainText()

    def test_downloading_is_still_available(self, editor):
        tabs = [editor.preview_tabs.tabText(i) for i in range(editor.preview_tabs.count())]

        assert tabs == ['📡  Latest mailing list', '✍️  Your own text']
        assert editor.fetch_button.isEnabled()


def test_highlighted_html_keeps_only_the_highlights():
    text = f'a < b & {AbstractEnclosure[0]}qubit{AbstractEnclosure[1]} <script>'

    assert highlighted_html(text) == f'a &lt; b &amp; {AbstractEnclosure[0]}qubit{AbstractEnclosure[1]} &lt;script&gt;'


def test_abstract_excerpt():
    highlight = AbstractEnclosure[0] + '{}' + AbstractEnclosure[1]
    summary = 'A' * 100 + ' we study ' + highlight.format('spin qubits') + ' with x<y, z>w and ' + highlight.format(
        'holes') + 'B' * 100

    excerpt = abstract_excerpt(summary, context=30)

    # Around the first highlight, shortened on both sides
    assert excerpt.startswith('…') and excerpt.endswith('…')
    assert ' we study <b>spin qubits</b> with x' in excerpt
    assert 'x&lt;y, z&gt;w' in excerpt  # The < > of the abstract are kept, escaped
    assert 'span' not in excerpt  # The other highlights are removed
    assert len(excerpt.split('</b>')[1]) - excerpt.count('&') * 3 <= 31  # About `context` characters after
    assert abstract_excerpt('No highlight') == ''


def test_outcome_enum_is_used(win):
    assert Outcome.FINISHED.value == 'finished'


class TestDatePicker:
    def test_both_calendars_shade_the_chosen_range(self, win):
        start, end = QtCore.QDate(2026, 9, 7), QtCore.QDate(2026, 9, 18)
        win.date_0_edit.setDate(start)
        win.date_f_edit.setDate(end)
        for edit in (win.date_0_edit, win.date_f_edit):
            calendar = edit.calendarWidget()
            assert (calendar.range_start, calendar.range_end) == (start, end)

    def test_today_closes_the_popup_with_the_date(self, win, qtbot):
        win.custom_dates_radio.setChecked(True)
        win.date_f_edit.setDate(QtCore.QDate.currentDate().addDays(-10))
        win.show()
        qtbot.waitExposed(win)
        edit = win.date_f_edit
        # A click on the arrow opens the calendar popup
        arrow = QtCore.QPoint(edit.width() - 8, edit.height() // 2)
        qtbot.mouseClick(edit, QtCore.Qt.MouseButton.LeftButton, pos=arrow)
        calendar = edit.calendarWidget()
        qtbot.waitUntil(calendar.isVisible)
        qtbot.mouseClick(calendar.today_button, QtCore.Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: not calendar.isVisible())
        assert edit.date() == QtCore.QDate.currentDate()

    def test_the_last_day_is_after_the_first_one(self, win):
        win.date_0_edit.setDate(QtCore.QDate(2026, 9, 1))
        win.date_f_edit.setDate(QtCore.QDate(2026, 9, 10))
        win.date_0_edit.setDate(QtCore.QDate(2026, 9, 14))  # After the last day, which moves to the next day
        assert win.date_f_edit.minimumDate() == QtCore.QDate(2026, 9, 15)
        assert win.date_f_edit.date() == QtCore.QDate(2026, 9, 15)
        assert win.date_0_edit.maximumDate() < QtCore.QDate.currentDate()

    def test_choosing_the_first_day_opens_the_calendar_of_the_last_one(self, win, qtbot):
        win.custom_dates_radio.setChecked(True)
        win.show()
        qtbot.waitExposed(win)
        win.date_0_edit.open_calendar()
        start_calendar, end_calendar = win.date_0_edit.calendarWidget(), win.date_f_edit.calendarWidget()
        qtbot.waitUntil(start_calendar.isVisible)
        start_calendar.choose_today()  # As a click on a day
        qtbot.waitUntil(end_calendar.isVisible)
        assert not start_calendar.isVisible()
        assert end_calendar.chooses == 'end'
