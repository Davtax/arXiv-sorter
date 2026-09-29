"""
Messages panel of the window: the messages of arXiv-sorter with an icon and a color for each level, clickable links, and
the summary of the run.
"""
import html
import re
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import QTextBrowser, QWidget

from arxiv_sorter.gui.summary import Outcome, Summary, describe_file
from arxiv_sorter.protocol import Level

OUTCOME_LEVELS = {Outcome.FINISHED: Level.SUCCESS, Outcome.ERRORS: Level.ERROR, Outcome.STOPPED: Level.WARNING,
                  Outcome.FAILED: Level.ERROR}

MAX_BLOCKS = 20000  # Oldest messages are dropped beyond this, to keep the window responsive
URL_PATTERN = re.compile(r'(https?://[^\s<>"]+[^\s<>".,;:)])')

# Colors for light and dark themes
COLORS = {
    False: {Level.STEP: '#1a5fb4', Level.SUCCESS: '#26792b', Level.WARNING: '#9a5b00', Level.ERROR: '#c01c28'},
    True: {Level.STEP: '#78aeed', Level.SUCCESS: '#8ff0a4', Level.WARNING: '#f8c35a', Level.ERROR: '#ff7b7b'},
}


def is_dark(palette: QPalette) -> bool:
    return palette.color(QPalette.ColorRole.Base).lightness() < 128  # Background of the messages


def linkify(text: str) -> str:
    """
    Escape the text for HTML, turning the web addresses into links.
    """
    parts = URL_PATTERN.split(text)
    return ''.join(f'<a href="{html.escape(part)}">{html.escape(part)}</a>' if i % 2 else html.escape(part)
                   for i, part in enumerate(parts))


def file_link(path: Path, text: str | None = None) -> str:
    url = QUrl.fromLocalFile(str(path)).toString()
    return f'<a href="{html.escape(url)}">{html.escape(text or str(path))}</a>'


class LogView(QTextBrowser):
    """
    The colors depend on the theme, so the content is kept as records, and drawn again when the theme changes.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setOpenLinks(False)  # Files and web pages are opened with the default application
        self.anchorClicked.connect(QDesktopServices.openUrl)
        self.document().setMaximumBlockCount(MAX_BLOCKS)
        self.document().setDocumentMargin(8)
        self.setPlaceholderText('The messages of arXiv-sorter appear here. Choose the folders and options above, '
                                'and press Run.')
        self.records: deque[tuple[Callable[..., str], tuple]] = deque(maxlen=MAX_BLOCKS)

    def _add(self, render: Callable[..., str], *args):
        self.records.append((render, args))
        self._append_html(render(*args))

    def clear(self):
        self.records.clear()
        super().clear()

    def redraw(self):
        """
        Draw the content again with the colors of the current theme, keeping the scroll position.
        """
        scroll_bar = self.verticalScrollBar()
        at_bottom = scroll_bar.value() >= scroll_bar.maximum() - 4
        position = scroll_bar.value()
        super().clear()
        for render, args in self.records:
            self.append(render(*args))
        scroll_bar.setValue(scroll_bar.maximum() if at_bottom else position)

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self.redraw()

    def _color(self, level: Level) -> str | None:
        return COLORS[is_dark(self.palette())].get(level)

    def _muted(self) -> str:
        """
        Secondary text color: halfway between the text and the background, so it works with any theme.
        """
        text = self.palette().color(QPalette.ColorRole.Text)
        base = self.palette().color(QPalette.ColorRole.Base)
        return QColor((text.red() + base.red()) // 2, (text.green() + base.green()) // 2,
                      (text.blue() + base.blue()) // 2).name()

    def _append_html(self, content: str):
        scroll_bar = self.verticalScrollBar()
        at_bottom = scroll_bar.value() >= scroll_bar.maximum() - 4
        self.append(content)
        if at_bottom:  # Follow the new messages, unless the user scrolled up to read older ones
            scroll_bar.setValue(scroll_bar.maximum())

    def add_message(self, level: Level, text: str, icon: str = ''):
        self._add(self._render_message, level, text, icon, datetime.now())

    def add_plain(self, text: str):
        """
        Output that is not a message of arXiv-sorter (e.g. of Python or Java), shown as it is.
        """
        self._add(self._render_plain, text)

    def add_summary(self, summary: Summary):
        self._add(self._render_summary, summary)

    def _render_message(self, level: Level, text: str, icon: str, time: datetime) -> str:
        muted = self._muted()
        time_html = f'<span style="color:{muted}; font-size:small">{time:%H:%M:%S}</span>&nbsp;&nbsp;'
        icon_html = f'{html.escape(icon)}&nbsp;' if icon else ''
        body = linkify(text)

        if level is Level.STEP:
            style = f'color:{self._color(level)}; font-size:large'
            return f'<p style="margin-top:10px">{time_html}<b style="{style}">{icon_html}{body}</b></p>'
        if level is Level.DETAIL:
            return (f'<p>{time_html}<span style="color:{muted}; font-family:monospace">&nbsp;&nbsp;&nbsp;{body}'
                    '</span></p>')

        color = self._color(level)
        style = f'color:{color};' if color else ''
        if level is Level.ERROR:
            style += ' font-weight:bold;'
        return f'<p>{time_html}<span style="{style}">{icon_html}{body}</span></p>'

    def _render_plain(self, text: str) -> str:
        return f'<p style="color:{self._muted()}; font-family:monospace; white-space:pre">{html.escape(text)}</p>'

    def _render_summary(self, summary: Summary) -> str:
        color = self._color(OUTCOME_LEVELS[summary.outcome])
        rows = ''.join(f'<tr><td>📄&nbsp;{file_link(file.path, file.path.name)}</td>'
                       f'<td style="padding-left:16px">{html.escape(describe_file(file))}</td></tr>'
                       for file in summary.files)
        folder = ''
        if summary.files:
            folder = (f'<p>📂 Saved in {file_link(summary.folder)}</p>' if summary.folder is not None
                      else '<p>📂 Saved in several folders</p>')

        headline = (f'<p style="margin-top:6px"><b style="color:{color}; font-size:large">{summary.icon}&nbsp;'
                    f'{html.escape(summary.headline)}</b></p>')
        table = f'<table style="margin-left:8px">{rows}</table>' if rows else ''
        return f'<hr>{headline}{table}{folder}'
