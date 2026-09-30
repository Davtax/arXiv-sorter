"""
Messages panel of the window: the messages of arXorter with an icon and a color for each level, clickable links (web
addresses and paths), and the summary of the run.
"""
import functools
import html
import os
import re
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import QTextBrowser, QWidget

from arxorter.gui.summary import Outcome, Summary, describe_file
from arxorter.protocol import Level

OUTCOME_LEVELS = {Outcome.FINISHED: Level.SUCCESS, Outcome.ERRORS: Level.ERROR, Outcome.STOPPED: Level.WARNING,
                  Outcome.FAILED: Level.ERROR}

MAX_BLOCKS = 20000  # Oldest messages are dropped beyond this, to keep the window responsive
URL_PATTERN = re.compile(r'(https?://[^\s<>"]+[^\s<>".,;:)])')

# Start of an absolute path, at the start of a word: a drive (C:\ or C:/), a network share (\\server) or the root (/)
PATH_START = re.compile(r'(?<![\w/\\:.])(?:[A-Za-z]:[\\/]|\\\\\w|/(?=[^\s/]))')
PATH_STOP = '"<>|*?`\n'  # Characters that cannot be in a path, e.g. the quotes around the paths of the tracebacks
TRAILING = '.,;:!)]}\''  # Punctuation that usually follows a path in a sentence
MAX_PATH_SPACES = 30  # A path can have spaces, so it ends at one of the next spaces (the longest path that exists)

# Opened in their folder instead, so that clicking a link never runs a program
PROGRAM_SUFFIXES = {'.app', '.bat', '.cmd', '.com', '.command', '.cpl', '.exe', '.jar', '.js', '.lnk', '.msi', '.ps1',
                    '.py', '.pyw', '.scr', '.sh', '.vbs'}

# Colors for light and dark themes
COLORS = {
    False: {Level.STEP: '#1a5fb4', Level.SUCCESS: '#26792b', Level.WARNING: '#9a5b00', Level.ERROR: '#c01c28'},
    True: {Level.STEP: '#78aeed', Level.SUCCESS: '#8ff0a4', Level.WARNING: '#f8c35a', Level.ERROR: '#ff7b7b'},
}


def is_dark(palette: QPalette) -> bool:
    return palette.color(QPalette.ColorRole.Base).lightness() < 128  # Background of the messages


def linkify(text: str) -> str:
    """
    Escape the text for HTML, turning the web addresses and the paths that exist into links.
    """
    parts = URL_PATTERN.split(text)
    return ''.join(f'<a href="{html.escape(part)}">{html.escape(part)}</a>' if i % 2 else link_paths(part)
                   for i, part in enumerate(parts))


def link_paths(text: str) -> str:
    """
    Escape the text for HTML, turning the paths that exist into links.
    """
    pieces, position = [], 0
    for start, end in find_paths(text):
        pieces.append(html.escape(text[position:start]))
        pieces.append(file_link(Path(text[start:end]), text[start:end]))
        position = end
    pieces.append(html.escape(text[position:]))
    return ''.join(pieces)


@functools.lru_cache(maxsize=4096)  # The messages are drawn again when the theme changes
def find_paths(text: str) -> tuple[tuple[int, int], ...]:
    """
    Start and end of the absolute paths in the text that exist.
    """
    found, position = [], 0
    while match := PATH_START.search(text, position):
        start = match.start()
        stop = next((i for i in range(start, len(text)) if text[i] in PATH_STOP), len(text))
        length = existing_path_length(text[start:stop])
        if length:
            found.append((start, start + length))
            position = start + length
        else:
            position = match.end()
    return tuple(found)


def existing_path_length(text: str) -> int:
    """
    Length of the longest start of the text that is an existing path (0 if none). As paths can have spaces, it is
    tried up to each space, without and with the punctuation that follows it in a sentence (first without, as Windows
    ignores the dots at the end of a path).
    """
    ends = [match.start() for match in re.finditer(r'\s', text)][:MAX_PATH_SPACES] + [len(text)]
    for end in sorted(set(ends), reverse=True):
        for candidate in dict.fromkeys((text[:end].rstrip(TRAILING), text[:end])):
            if candidate and path_exists(candidate):
                return len(candidate)
    return 0


def path_exists(text: str) -> bool:
    try:
        return Path(text).exists()
    except (OSError, ValueError):  # E.g. not valid in this system
        return False


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
        self.anchorClicked.connect(self.open_link)
        self.document().setMaximumBlockCount(MAX_BLOCKS)
        self.document().setDocumentMargin(8)
        self.setPlaceholderText('The messages of arXorter appear here. Choose the folders and options above, '
                                'and press Run.')
        self.records: deque[tuple[Callable[..., str], tuple]] = deque(maxlen=MAX_BLOCKS)

    @staticmethod
    def open_link(url: QUrl):
        """
        Open the link with the default application. Programs and scripts are not run: their folder is opened instead.
        """
        if url.isLocalFile():
            path = Path(url.toLocalFile())
            is_program = path.suffix.lower() in PROGRAM_SUFFIXES or (
                os.name != 'nt' and not path.suffix and path.is_file() and os.access(path, os.X_OK))
            if is_program:
                url = QUrl.fromLocalFile(str(path.parent))
        QDesktopServices.openUrl(url)

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
        Output that is not a message of arXorter (e.g. of Python or Java), shown as it is.
        """
        self._add(self._render_plain, text)

    def add_summary(self, summary: Summary, log_path: Path | None = None):
        """
        Summary of the run, with a link to the log file if given (e.g. to report a problem).
        """
        self._add(self._render_summary, summary, log_path)

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
        return f'<p style="color:{self._muted()}; font-family:monospace; white-space:pre">{linkify(text)}</p>'

    def _render_summary(self, summary: Summary, log_path: Path | None) -> str:
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
        log = f'<p>📜 All the details are in the log file {file_link(log_path, log_path.name)}</p>' if log_path else ''
        return f'<hr>{headline}{table}{folder}{log}'
