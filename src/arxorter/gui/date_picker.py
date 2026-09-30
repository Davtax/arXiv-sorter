"""
Calendar of the date edits: a single header with the month (whose menu jumps to the recent months) and the arrows, the
selected day in a circle of the accent color, today in a ring, the chosen date range shaded, and a button to go back
to today. The weekends are muted, since the mailing lists are dated from Monday to Friday. The colors come from the
palette, so it follows the theme and the style of every system.
"""
from PySide6.QtCore import QDate, QEvent, QLocale, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPalette, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

CELL_SIZE = 34  # Square cells, large enough for the circle around two digits
RANGE_ALPHA = 45  # Opacity (of 255) of the accent color that shades the date range
MENU_MONTHS = 24  # Recent months listed in the menu of the title (the arrows go further back)
# Flat on every style (the macOS style draws a bevel around the tool buttons), with the colors of the palette
HEADER_BUTTON_STYLE = '''
    QToolButton { border: none; border-radius: 6px; padding: 3px 8px; background: transparent; }
    QToolButton:hover, QToolButton:pressed { background: palette(midlight); }
    QToolButton:disabled { color: palette(mid); }
    QToolButton::menu-indicator { image: none; width: 0; }
'''
WEEKEND = (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday)


def accent_color(palette: QPalette) -> QColor:
    """
    Accent color of the system (the highlight of the selections is paler on macOS), or the highlight otherwise.
    """
    return palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Accent)


def muted(color: QColor, alpha: int = 110) -> QColor:
    color = QColor(color)
    color.setAlpha(alpha)
    return color


class DatePicker(QCalendarWidget):
    """
    Calendar to use as the popup of a QDateEdit (setCalendarWidget), or on its own.
    """
    today_chosen = Signal(QDate)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.range_start = QDate()
        self.range_end = QDate()
        # Which end of the range this calendar chooses ('start', 'end' or ''): hovering a day previews the range that
        # choosing it would give, as in the date pickers of booking websites
        self.chooses = ''
        self.hovered = QDate()

        self.setNavigationBarVisible(False)  # Replaced by the header below
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setGridVisible(False)
        self.setFirstDayOfWeek(QLocale().firstDayOfWeek())

        self.view = self.findChild(QAbstractItemView)
        if self.view is not None:
            self.view.setMouseTracking(True)
            self.view.viewport().installEventFilter(self)
            self.view.setMinimumSize(7 * CELL_SIZE, 7 * CELL_SIZE)  # Six weeks and the names of the days

        self.previous_button = self._arrow_button('‹', 'Previous month', -1)
        self.next_button = self._arrow_button('›', 'Next month', 1)
        self.title_button = QToolButton()
        self.title_button.setAutoRaise(True)
        self.title_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.title_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.title_button.setToolTip('Go to another month')
        self.title_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_font = self.title_button.font()
        title_font.setBold(True)
        self.title_button.setFont(title_font)
        self.month_menu = QMenu(self.title_button)
        self.month_menu.aboutToShow.connect(self._fill_month_menu)
        self.title_button.setMenu(self.month_menu)

        header = QHBoxLayout()
        header.setContentsMargins(6, 6, 6, 0)
        header.addWidget(self.previous_button)
        header.addWidget(self.title_button, 1)
        header.addWidget(self.next_button)

        self.today_button = QPushButton('Today')
        self.today_button.setToolTip('Choose today (or the latest day allowed)')
        self.today_button.clicked.connect(self.choose_today)
        footer = QHBoxLayout()
        footer.setContentsMargins(6, 0, 6, 6)
        footer.addStretch()
        footer.addWidget(self.today_button)

        layout = self.layout()
        if isinstance(layout, QVBoxLayout):  # The layout of QCalendarWidget: navigation bar (hidden) and view
            layout.insertLayout(0, header)
            layout.addLayout(footer)

        # The whole calendar (also behind the header and the button) on the color of the days
        self.setBackgroundRole(QPalette.ColorRole.Base)
        self.setAutoFillBackground(True)
        for button in (self.previous_button, self.title_button, self.next_button):
            button.setStyleSheet(HEADER_BUTTON_STYLE)

        self.currentPageChanged.connect(self._update_header)
        self._update_formats()
        self._update_header()

    def _arrow_button(self, text: str, tooltip: str, months: int) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        font = button.font()
        font.setPointSizeF(font.pointSizeF() * 1.4)
        button.setFont(font)
        button.setFixedWidth(32)
        button.setAutoRepeat(True)
        button.clicked.connect(lambda: self.showNextMonth() if months > 0 else self.showPreviousMonth())
        return button

    # ---------------------------------------------------------------- header
    def page(self) -> QDate:
        return QDate(self.yearShown(), self.monthShown(), 1)

    def _update_header(self, *_):
        self.title_button.setText(f"{QLocale().toString(self.page(), 'MMMM yyyy')}  ▾")
        first, last = self.minimumDate(), self.maximumDate()
        self.previous_button.setEnabled(self.page() > QDate(first.year(), first.month(), 1))
        self.next_button.setEnabled(self.page().addMonths(1) <= last)

    def _fill_month_menu(self):
        self.month_menu.clear()
        last = self.maximumDate()
        month = QDate(last.year(), last.month(), 1)
        for _ in range(MENU_MONTHS):
            if month.addMonths(1).addDays(-1) < self.minimumDate():
                break
            action = QAction(QLocale().toString(month, 'MMMM yyyy'), self.month_menu)
            action.setCheckable(True)
            action.setChecked(month == self.page())
            action.triggered.connect(lambda _checked, shown=month: self.setCurrentPage(shown.year(), shown.month()))
            self.month_menu.addAction(action)
            month = month.addMonths(-1)

    def showEvent(self, event):  # noqa: N802 (Qt name)
        # The date edit changes the allowed dates from C++, which does not call the Python methods, so the arrows are
        # updated when the calendar is shown. So are the colors: a new style (when the theme changes) resets the ones of
        # the view after the calendar was notified
        self._update_header()
        self._update_formats()
        super().showEvent(event)

    def choose_today(self):
        """
        Select today (within the allowed dates) and confirm it, which closes the popup of a date edit.
        """
        today = min(max(QDate.currentDate(), self.minimumDate()), self.maximumDate())
        self.setSelectedDate(today)
        self.today_chosen.emit(today)
        self.clicked.emit(today)  # As a click on the day: the date edit takes it and closes the popup

    # ----------------------------------------------------------------- range
    def set_range(self, start: QDate, end: QDate):
        """
        Days shaded as the chosen date range (from the first date edit to the second one).
        """
        self.range_start, self.range_end = start, end
        self.updateCells()

    def shown_range(self) -> tuple[QDate, QDate]:
        """
        The chosen range, or the one that choosing the hovered day would give.
        """
        start, end = self.range_start, self.range_end
        if self.hovered.isValid() and self.chooses == 'end' and self.hovered > start:
            end = self.hovered
        elif self.hovered.isValid() and self.chooses == 'start' and self.hovered < end:
            start = self.hovered
        return start, end

    def in_range(self, date: QDate) -> bool:
        start, end = self.shown_range()
        return start.isValid() and end.isValid() and start <= date <= end

    def date_at(self, position: QPoint) -> QDate:
        """
        Day of the cell at the position of the view (invalid for the names of the days, or outside the cells). The
        view shows the day of the month in each cell, and the first and last rows may have days of other months.
        """
        if self.view is None:
            return QDate()
        index = self.view.indexAt(position)
        try:
            day = int(index.data())
        except (TypeError, ValueError):
            return QDate()
        month = self.page()
        if index.row() <= 2 and day > 20:
            month = month.addMonths(-1)
        elif index.row() >= 4 and day < 15:
            month = month.addMonths(1)
        return QDate(month.year(), month.month(), day)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt name)
        if self.view is not None and watched is self.view.viewport():
            if event.type() == QEvent.Type.MouseMove:
                date = self.date_at(event.position().toPoint())
                if not self.minimumDate() <= date <= self.maximumDate():
                    date = QDate()
                if date != self.hovered:
                    self.hovered = date
                    self.updateCells()
            elif event.type() == QEvent.Type.Leave and self.hovered.isValid():
                self.hovered = QDate()
                self.updateCells()
        return super().eventFilter(watched, event)

    def hideEvent(self, event):  # noqa: N802 (Qt name)
        self.hovered = QDate()
        super().hideEvent(event)

    # ---------------------------------------------------------------- colors
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (event.Type.PaletteChange, event.Type.StyleChange):
            self._update_formats()

    def _update_formats(self):
        """
        Colors of the names of the days, from the palette (the default ones are red for the weekend, on a grey row).
        """
        palette = self.palette()
        header = QTextCharFormat()
        header.setBackground(palette.brush(QPalette.ColorRole.Base))
        header.setFontWeight(QFont.Weight.DemiBold)
        self.setHeaderTextFormat(header)
        text = palette.color(QPalette.ColorRole.Text)
        for day in Qt.DayOfWeek:  # Only used by the names of the days: the cells are painted by paintCell
            weekday = QTextCharFormat()
            weekday.setForeground(muted(text, 110 if day in WEEKEND else 170))
            self.setWeekdayTextFormat(day, weekday)
        if self.view is not None:
            view_palette = self.view.palette()
            view_palette.setBrush(QPalette.ColorRole.AlternateBase, palette.brush(QPalette.ColorRole.Base))
            self.view.setPalette(view_palette)
        self.updateCells()

    # --------------------------------------------------------------- drawing
    def paintCell(self, painter: QPainter, rect: QRect, date: QDate):  # noqa: N802 (Qt name)
        palette = self.palette()
        accent = accent_color(palette)
        enabled = self.isEnabled() and self.minimumDate() <= date <= self.maximumDate()
        this_month = date.month() == self.monthShown() and date.year() == self.yearShown()
        today = date == QDate.currentDate()
        hovered = date == self.hovered and enabled
        # Both ends of the range are filled (the first one too in the calendar of the last one, where it cannot be
        # chosen), except the hovered day, which only previews one
        start, end = self.shown_range()
        if start.isValid() and end.isValid():
            selected = this_month and date in (start, end) and not hovered
        else:
            selected = this_month and date == self.selectedDate()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, palette.brush(QPalette.ColorRole.Base))

        size = min(rect.width(), rect.height()) - 4
        circle = QRectF(0, 0, size, size)
        circle.moveCenter(QRectF(rect).center())

        if this_month and self.in_range(date):
            band = QRectF(rect.left(), circle.top(), rect.width(), circle.height())
            if date == start or date.dayOfWeek() == self.firstDayOfWeek().value:
                band.setLeft(circle.center().x())
            if date == end or date.addDays(1).dayOfWeek() == self.firstDayOfWeek().value:
                band.setRight(circle.center().x())
            shape = QPainterPath()
            shape.addRect(band)
            if band.width() < rect.width():  # Rounded end of the band
                cap = QPainterPath()
                cap.addEllipse(circle)
                shape = shape.united(cap)
            painter.fillPath(shape, muted(accent, RANGE_ALPHA))

        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent if self.isEnabled() else muted(accent))
            painter.drawEllipse(circle)
        elif hovered:
            painter.setPen(QPen(muted(accent, 160), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(circle.adjusted(1, 1, -1, -1))
        elif today:
            painter.setPen(QPen(accent, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(circle.adjusted(1, 1, -1, -1))

        if selected:
            color = QColor(Qt.GlobalColor.white if accent.lightnessF() < 0.6 else Qt.GlobalColor.black)
        else:
            color = palette.color(QPalette.ColorRole.Text)
            if not this_month or not enabled:
                color = muted(color, 70)
            elif date.dayOfWeek() in (day.value for day in WEEKEND):
                color = muted(color, 130)
        font = QFont(self.font())
        font.setBold(selected or today)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(QRectF(rect), Qt.AlignmentFlag.AlignCenter, str(date.day()))
        painter.restore()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        hint = super().sizeHint()
        return hint.expandedTo(QSize(7 * CELL_SIZE + 12, 8 * CELL_SIZE + 60))

