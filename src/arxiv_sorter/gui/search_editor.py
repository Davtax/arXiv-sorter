"""
Editor of the search files (keywords, authors and categories), with the mistakes checked while typing and a preview of
the submissions of the latest mailing list that would match.
"""
import html
import re
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QColor, QDesktopServices, QFontDatabase, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from arxiv_sorter.gui.log_view import COLORS, is_dark
from arxiv_sorter.gui.search_files import SEARCH_FILES, describe
from arxiv_sorter.preview import LatestSubmissions, custom_entry, fetch_latest, matching_entries
from arxiv_sorter.protocol import Level
from arxiv_sorter.search_terms import Kind, Problem, Severity, check_lines
from arxiv_sorter.sorting import AbstractEnclosure, AuthorEnclosure, TitleEnclosure
from arxiv_sorter.user_files import normalize_lines

HELP = {
    Kind.KEYWORDS: 'One keyword per line, searched in the titles and abstracts (case-insensitive). Lines are '
                   '<a href="https://regex101.com">regular expressions</a>, e.g. <code>spin[- ]orbit</code>. Join '
                   'terms with <code>&amp;</code> to require all of them, e.g. <code>spin qubit&amp;germanium</code>. '
                   'Lines starting with <code>#</code> are ignored. The first lines have priority in the sorting.',
    Kind.AUTHORS: 'One author per line, searched as full words, without accents nor case. The surname is usually '
                  'enough, e.g. <code>Loss</code>. A pattern like <code>M[^,]* +Ares</code> matches M. Ares and '
                  'Maria Ares, but not D. Ares. Lines starting with <code>#</code> are ignored.',
    Kind.CATEGORIES: 'One <a href="https://arxiv.org/category_taxonomy">arXiv category</a> per line, e.g. '
                     '<code>quant-ph</code> or <code>cond-mat.mes-hall</code>. A group without subcategory, like '
                     '<code>cond-mat</code>, includes all of them. Empty: all the categories of arXiv.',
}
PLACEHOLDERS = {Kind.KEYWORDS: 'quantum dot\nspin[- ]orbit&spin qubit', Kind.AUTHORS: 'Loss\nM[^,]* +Ares',
                Kind.CATEGORIES: 'quant-ph\ncond-mat'}
PREVIEW_LIMIT = 50  # Matching submissions listed in the preview
HIGHLIGHT = re.compile(re.escape(AbstractEnclosure[0]) + '(.*?)' + re.escape(AbstractEnclosure[1]), re.DOTALL)
# Only the highlights added by the sorting: abstracts may contain < and > themselves (e.g. inequalities)
TAG = re.compile('|'.join(re.escape(tag) for tag in AbstractEnclosure))
ENCLOSURE_TAGS = [tag for enclosure in (TitleEnclosure, AuthorEnclosure, AbstractEnclosure) for tag in enclosure]
ENCLOSURE_TAG = re.compile('(' + '|'.join(re.escape(tag) for tag in ENCLOSURE_TAGS) + ')')  # All the highlights


def highlighted_html(text: str) -> str:
    """
    Text highlighted by the sorting, as HTML: everything is escaped except the highlights themselves, since the text
    may contain < > & (e.g. inequalities in arXiv titles, or anything written by the user).
    """
    return ''.join(part if i % 2 else html.escape(part) for i, part in enumerate(ENCLOSURE_TAG.split(text)))


def abstract_excerpt(summary: str, context: int = 70) -> str:
    """
    HTML excerpt of the abstract around its first highlighted keyword (see sorting.AbstractEnclosure), to show why a
    submission matches when the keyword is not in the title. Empty if the abstract has no match.
    """
    match = HIGHLIGHT.search(summary)
    if match is None:
        return ''
    before = TAG.sub('', summary[:match.start()])
    after = TAG.sub('', summary[match.end():])
    start = '…' if len(before) > context else ''
    end = '…' if len(after) > context else ''
    return (f'{start}{html.escape(before[-context:])}<b>{html.escape(TAG.sub("", match.group(1)))}</b>'
            f'{html.escape(after[:context])}{end}')


class FetchWorker(QObject):
    """
    Download of the latest mailing list, in a separate thread so the dialog keeps responding.
    """
    finished = Signal(object)  # LatestSubmissions | None
    failed = Signal(str)

    def __init__(self, categories: list[str]):
        super().__init__()
        self.categories = categories

    def run(self):
        try:
            self.finished.emit(fetch_latest(self.categories))
        except Exception as error:  # e.g. no connection
            self.failed.emit(str(error))


class SearchFileTab(QWidget):
    changed = Signal()

    def __init__(self, kind: Kind, path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind = kind
        self.path = path

        help_label = QLabel(HELP[kind])
        help_label.setWordWrap(True)
        help_label.setOpenExternalLinks(True)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlaceholderText(PLACEHOLDERS[kind])
        try:
            self.saved_text = path.read_text(encoding='utf-8')
        except OSError:
            self.saved_text = ''
        self.editor.setPlainText(self.saved_text)
        self.editor.textChanged.connect(self.changed)

        self.problems_label = QLabel()
        self.problems_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(self.editor, stretch=1)
        layout.addWidget(self.problems_label)

    def lines(self) -> list[str]:
        return self.editor.toPlainText().splitlines()

    def is_modified(self) -> bool:
        return self.editor.toPlainText() != self.saved_text

    def problems(self) -> list[Problem]:
        return check_lines(self.lines(), self.kind)

    def show_problems(self) -> list[Problem]:
        """
        Highlight the lines with mistakes, and list them below the editor.
        """
        problems = self.problems()
        colors = COLORS[is_dark(self.palette())]

        selections = []
        for problem in problems:
            selection = QTextEdit.ExtraSelection()
            color = QColor(colors[Level.ERROR if problem.severity is Severity.ERROR else Level.WARNING])
            color.setAlpha(60)
            selection.format.setBackground(color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = QTextCursor(self.editor.document().findBlockByNumber(problem.line - 1))
            selections.append(selection)
        self.editor.setExtraSelections(selections)

        if problems:
            self.problems_label.setText('<br>'.join(
                f'<span style="color:{colors[Level.ERROR if problem.severity is Severity.ERROR else Level.WARNING]}">'
                f'{"❌" if problem.severity is Severity.ERROR else "⚠️"} Line {problem.line}: '
                f'{html.escape(problem.message)} ({html.escape(problem.text.strip())})</span>' for problem in problems))
        else:
            count = len(normalize_lines(self.lines()))
            search_file = next(file for file in SEARCH_FILES if file.filename == self.kind.filename)
            self.problems_label.setText(f'✅ {describe(search_file, count)}, no mistakes')
        return problems

    def go_to_line(self, line: int):
        cursor = QTextCursor(self.editor.document().findBlockByNumber(max(line - 1, 0)))
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def save(self):
        text = self.editor.toPlainText()
        if text and not text.endswith('\n'):
            text += '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding='utf-8')
        self.saved_text = self.editor.toPlainText()


class SearchFilesEditor(QDialog):
    """
    Dialog to edit the three search files of a folder.
    """

    def __init__(self, folder: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.folder = folder
        self.setWindowTitle(f'Search files — {folder}')
        self.resize(1000, 700)
        self.latest: LatestSubmissions | None = None
        self.fetch_thread: QThread | None = None
        self.worker: FetchWorker | None = None

        self.check_timer = QTimer(self)  # Check once the user stops typing
        self.check_timer.setSingleShot(True)
        self.check_timer.setInterval(300)
        self.check_timer.timeout.connect(self.refresh)

        self.tabs = QTabWidget()
        self.file_tabs: dict[Kind, SearchFileTab] = {}
        for kind in Kind:
            tab = SearchFileTab(kind, folder / kind.filename)
            tab.changed.connect(self.check_timer.start)
            self.file_tabs[kind] = tab
            self.tabs.addTab(tab, '')

        self.preview_tabs = QTabWidget()
        self.preview_tabs.addTab(self._build_latest_tab(), '📡  Latest mailing list')
        self.preview_tabs.addTab(self._build_own_text_tab(), '✍️  Your own text')

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(QLabel('<b>🔍 Preview</b> — test your keywords and authors (with the unsaved '
                                        'changes)'))
        preview_layout.addWidget(self.preview_tabs, stretch=1)

        splitter = QSplitter()
        splitter.addWidget(self.tabs)
        splitter.addWidget(preview_panel)
        splitter.setSizes([560, 440])

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.close)
        open_folder = self.buttons.addButton('Open the folder', QDialogButtonBox.ButtonRole.HelpRole)
        open_folder.clicked.connect(lambda: _open_folder(folder))

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, stretch=1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.buttons)
        layout.addLayout(bottom)

        self.refresh()

    def _build_latest_tab(self) -> QWidget:
        self.fetch_button = QPushButton('📡  Download the latest mailing list')
        self.fetch_button.setToolTip('Download the submissions of the latest mailing list in your categories, to '
                                     'see which ones your keywords and authors would find')
        self.fetch_button.clicked.connect(self.fetch)
        self.preview_status = QLabel('See which submissions of the latest mailing list your terms would find.')
        self.preview_status.setWordWrap(True)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self.fetch_button)
        layout.addWidget(self.preview_status)
        layout.addWidget(self.preview, stretch=1)
        return tab

    def _build_own_text_tab(self) -> QWidget:
        self.own_title = QLineEdit()
        self.own_title.setPlaceholderText('e.g. Hole spin qubits in germanium quantum dots')
        self.own_authors = QLineEdit()
        self.own_authors.setPlaceholderText('Separated by commas, e.g. Daniel Loss, Guido Burkard')
        self.own_abstract = QPlainTextEdit()
        self.own_abstract.setPlaceholderText('Paste or write an abstract')
        for field in (self.own_title, self.own_authors):
            field.textChanged.connect(self.check_timer.start)
        self.own_abstract.textChanged.connect(self.check_timer.start)
        self.own_result = QTextBrowser()

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)  # Not the default on macOS
        form.addRow('Title:', self.own_title)
        form.addRow('Authors:', self.own_authors)
        form.addRow('Abstract:', self.own_abstract)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel('Write or paste a submission, to check whether your terms would find it.'))
        layout.addLayout(form, stretch=2)
        layout.addWidget(self.own_result, stretch=3)
        return tab

    def open_file(self, filename: str, line: int | None = None):
        kind = Kind(Path(filename).stem)
        self.tabs.setCurrentWidget(self.file_tabs[kind])
        if line is not None:
            self.file_tabs[kind].go_to_line(line)

    def refresh(self):
        """
        Check the three files, update the tab titles and the preview.
        """
        for index, (kind, tab) in enumerate(self.file_tabs.items()):
            problems = tab.show_problems()
            mark = '❌ ' if any(p.severity is Severity.ERROR for p in problems) else '⚠️ ' if problems else ''
            self.tabs.setTabText(index, f'{mark}{kind.filename}{" •" if tab.is_modified() else ""}')
        self.update_preview()

    def categories(self) -> list[str]:
        return normalize_lines(self.file_tabs[Kind.CATEGORIES].lines())

    # --------------------------------------------------------------- preview
    def fetch(self):
        if self.fetch_thread is not None:
            return
        self.fetch_button.setEnabled(False)
        categories = self.categories()
        self.preview_status.setText(f'⏳ Downloading the latest mailing list of '
                                    f'{", ".join(categories) or "all the categories"} …')

        self.fetch_thread = QThread(self)
        self.worker = FetchWorker(categories)
        self.worker.moveToThread(self.fetch_thread)
        self.fetch_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._fetched)
        self.worker.failed.connect(self._fetch_failed)
        self.worker.finished.connect(self._stop_thread)
        self.worker.failed.connect(self._stop_thread)
        self.fetch_thread.start()

    def _stop_thread(self):
        if self.fetch_thread is not None:
            self.fetch_thread.quit()
            self.fetch_thread.wait()
            self.fetch_thread = None
            self.worker = None
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText('📡  Download again')

    def _fetched(self, latest: LatestSubmissions | None):
        self.latest = latest
        if latest is None:
            self.preview_status.setText('📭 No submissions found in the last mailing lists. Check the categories.')
        self.update_preview()

    def _fetch_failed(self, message: str):
        self.preview_status.setText(f'❌ Unable to download the mailing list: {html.escape(message)}')

    def update_preview(self):
        self.update_own_text_preview()
        if self.latest is None:
            return

        entries = self.latest.entries
        matches = matching_entries(entries, self.file_tabs[Kind.KEYWORDS].lines(),
                                   self.file_tabs[Kind.AUTHORS].lines())
        day = f'{self.latest.date:%a} {self.latest.date.day} {self.latest.date:%b %Y}'
        self.preview_status.setText(f'✨ <b>{len(matches)}</b> of the {len(entries)} submissions of {day} match '
                                    'your keywords or authors.')

        rows = []
        for entry in matches[:PREVIEW_LIMIT]:
            link = html.escape(entry.get('link', entry.id))
            excerpt = abstract_excerpt(entry.summary)
            excerpt_html = f'<br><small><i>{excerpt}</i></small>' if excerpt else ''
            rows.append(f'<p style="margin-bottom:8px"><a href="{link}" style="text-decoration:none">'
                        f'<b>{highlighted_html(entry.title)}</b></a><br><small>{highlighted_html(entry.authors)}'
                        f'</small>{excerpt_html}</p>')
        if len(matches) > PREVIEW_LIMIT:
            rows.append(f'<p><i>… and {len(matches) - PREVIEW_LIMIT} more</i></p>')
        self.preview.setHtml(''.join(rows) or '<p><i>No submission matches yet.</i></p>')

    def update_own_text_preview(self):
        """
        Check whether the text written by the user would be found, highlighting the matches.
        """
        title, authors = self.own_title.text(), self.own_authors.text()
        abstract = self.own_abstract.toPlainText()
        if not (title.strip() or authors.strip() or abstract.strip()):
            self.own_result.setHtml('<p><i>The result appears here while you type.</i></p>')
            return

        entry = custom_entry(title, abstract, authors)
        matches = matching_entries([entry], self.file_tabs[Kind.KEYWORDS].lines(),
                                   self.file_tabs[Kind.AUTHORS].lines())
        colors = COLORS[is_dark(self.palette())]
        if matches:
            shown = matches[0]
            found_in = [name for name, text in (('title', shown.title), ('authors', shown.authors),
                                                ('abstract', shown.summary)) if '<span' in text]
            verdict = (f'<p style="color:{colors[Level.SUCCESS]}"><b>✅ It would be found</b> (matches in the '
                       f'{", ".join(found_in)})</p>')
        else:
            shown = entry
            verdict = (f'<p style="color:{colors[Level.ERROR]}"><b>❌ It would not be found</b> by your keywords nor '
                       'authors</p>')

        parts = [verdict]
        for label, text in (('Title', shown.title), ('Authors', shown.authors), ('Abstract', shown.summary)):
            if text:
                parts.append(f'<p><b>{label}:</b> {highlighted_html(text)}</p>')
        self.own_result.setHtml(''.join(parts))

    # ------------------------------------------------------------------ files
    def is_modified(self) -> bool:
        return any(tab.is_modified() for tab in self.file_tabs.values())

    def save(self) -> bool:
        errors = [problem for tab in self.file_tabs.values() for problem in tab.problems()
                  if problem.severity is Severity.ERROR]
        if errors:
            answer = QMessageBox.warning(
                self, 'Mistakes in the search files',
                f'There {"is 1 mistake" if len(errors) == 1 else f"are {len(errors)} mistakes"}, and arXiv-sorter '
                'will not run until they are fixed. Save anyway?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Save:
                return False
        try:
            for tab in self.file_tabs.values():
                if tab.is_modified():
                    tab.save()
        except OSError as error:
            QMessageBox.warning(self, 'Unable to save', str(error))
            return False
        self.refresh()
        return True

    def closeEvent(self, event: QCloseEvent):
        if self.is_modified():
            answer = QMessageBox.question(
                self, 'Unsaved changes', 'Save the changes to the search files?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel or (
                    answer == QMessageBox.StandardButton.Save and not self.save()):
                event.ignore()
                return
        if self.fetch_thread is not None:  # Let the download finish in the background before the dialog is deleted
            self.fetch_thread.quit()
            self.fetch_thread.wait(5000)
        event.accept()

    def reject(self):  # Escape key: same as closing the window
        self.close()


def _open_folder(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
