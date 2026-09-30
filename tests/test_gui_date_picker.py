import os
import sys

import pytest

if sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtCore = pytest.importorskip('PySide6.QtCore')

from arxiv_sorter.gui.date_picker import DatePicker  # noqa: E402

QDate = QtCore.QDate


@pytest.fixture(scope='module')
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def date_edit(app):
    edit = QtWidgets.QDateEdit(QDate(2026, 9, 22))
    edit.setCalendarPopup(True)
    edit.setCalendarWidget(DatePicker())
    edit.setMaximumDate(QDate(2026, 9, 30))
    yield edit
    edit.deleteLater()


def test_the_date_edit_uses_the_picker(date_edit):
    assert isinstance(date_edit.calendarWidget(), DatePicker)
    assert not date_edit.calendarWidget().isNavigationBarVisible()  # Replaced by its own header


def test_today_is_chosen_within_the_allowed_dates(date_edit):
    picker = date_edit.calendarWidget()
    chosen = []
    picker.clicked.connect(chosen.append)
    picker.choose_today()
    expected = min(QDate.currentDate(), date_edit.maximumDate())
    assert chosen == [expected]
    assert date_edit.date() == expected


def test_the_header_shows_the_month_and_moves_with_the_arrows(date_edit):
    picker = date_edit.calendarWidget()
    picker.setCurrentPage(2026, 9)
    assert picker.title_button.text().startswith(QtCore.QLocale().toString(QDate(2026, 9, 1), 'MMMM yyyy'))
    picker._update_header()  # As when the popup is shown
    assert not picker.next_button.isEnabled()  # October is after the maximum date
    picker.previous_button.click()
    assert (picker.yearShown(), picker.monthShown()) == (2026, 8)
    assert picker.next_button.isEnabled()


def test_the_menu_lists_the_recent_months(date_edit):
    picker = date_edit.calendarWidget()
    picker._fill_month_menu()
    actions = picker.month_menu.actions()
    assert actions[0].text() == QtCore.QLocale().toString(QDate(2026, 9, 1), 'MMMM yyyy')
    actions[3].trigger()
    assert (picker.yearShown(), picker.monthShown()) == (2026, 6)


def test_the_range_includes_both_ends(date_edit):
    picker = date_edit.calendarWidget()
    picker.set_range(QDate(2026, 9, 15), QDate(2026, 9, 22))
    assert picker.in_range(QDate(2026, 9, 15)) and picker.in_range(QDate(2026, 9, 22))
    assert not picker.in_range(QDate(2026, 9, 14)) and not picker.in_range(QDate(2026, 9, 23))


def test_the_cells_are_painted(date_edit):
    picker = date_edit.calendarWidget()
    picker.set_range(QDate(2026, 9, 15), QDate(2026, 9, 22))
    picker.resize(picker.sizeHint())
    assert not picker.grab().isNull()


def test_hovering_a_day_previews_the_range(date_edit):
    picker = date_edit.calendarWidget()
    picker.set_range(QDate(2026, 9, 14), QDate(2026, 9, 16))
    picker.chooses = 'end'
    picker.hovered = QDate(2026, 9, 24)
    assert picker.shown_range() == (QDate(2026, 9, 14), QDate(2026, 9, 24))
    picker.hovered = QDate(2026, 9, 10)  # Before the first day: not a range
    assert picker.shown_range() == (QDate(2026, 9, 14), QDate(2026, 9, 16))
    picker.chooses = 'start'
    assert picker.shown_range() == (QDate(2026, 9, 10), QDate(2026, 9, 16))


def test_the_day_under_the_mouse_is_found(date_edit):
    picker = date_edit.calendarWidget()
    picker.setCurrentPage(2026, 9)
    picker.resize(picker.sizeHint())
    picker.show()
    model = picker.view.model()
    days = {picker.date_at(picker.view.visualRect(model.index(row, column)).center())
            for row in range(model.rowCount()) for column in range(model.columnCount())}
    assert QDate() in days  # The names of the days
    assert {QDate(2026, 9, day) for day in range(1, 31)} <= days
    assert all(day.isValid() and abs(day.daysTo(QDate(2026, 9, 15))) < 45 for day in days - {QDate()})
    picker.hide()
