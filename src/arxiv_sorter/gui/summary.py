"""
Final message shown in the GUI when a run ends.
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Outcome(Enum):
    FINISHED = 'finished'
    ERRORS = 'errors'  # Finished, but some errors were reported
    STOPPED = 'stopped'  # By the user
    FAILED = 'failed'  # Crashed, or could not start


@dataclass
class WrittenFile:
    """
    Mailing list written by arXiv-sorter: a Markdown file, or a folder with a file per entry (--separate).
    """
    path: Path
    n_entries: int
    n_new: int

    @classmethod
    def from_message(cls, message: str) -> WrittenFile | None:
        """
        Parse the tagged line sent by arxiv_sorter.console.report_written (without the tag).
        """
        try:
            n_entries, n_new, path = message.split('\t', 2)
            return cls(Path(path), int(n_entries), int(n_new))
        except ValueError:
            return None


@dataclass
class Summary:
    outcome: Outcome
    status: str  # Short text for the status bar
    headline: str
    icon: str
    files: list[WrittenFile] = field(default_factory=list)

    @property
    def folder(self) -> Path | None:
        """
        Folder of the written files, if they are all in the same one.
        """
        folders = {file.path.parent for file in self.files}
        return folders.pop() if len(folders) == 1 else None

    def lines(self) -> list[str]:
        """
        Summary as plain text.
        """
        lines = [f'{self.icon} {self.headline}']
        width = max((len(file.path.name) for file in self.files), default=0)
        for file in self.files:
            lines.append(f'  {file.path.name:<{width}}  {describe_file(file)}')
        if self.files:
            lines.append(f'Saved in {self.folder}' if self.folder is not None else 'Saved in several folders')
        return lines


def format_duration(seconds: float) -> str:
    minutes, seconds = divmod(round(seconds), 60)
    return f'{minutes} min {seconds:02} s' if minutes else f'{seconds} s'


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return f'{count} {singular}' if count == 1 else f'{count} {plural_form or singular + "s"}'


def describe_file(file: WrittenFile) -> str:
    return f'{plural(file.n_entries, "entry", "entries")}, {file.n_new} new or matching your keywords'


def final_message(outcome: Outcome, elapsed: float, written: list[WrittenFile], n_warnings: int = 0) -> Summary:
    duration = format_duration(elapsed)
    sorted_lists = plural(len(written), 'mailing list')
    warnings = f' ({plural(n_warnings, "warning")}, see the messages above)' if n_warnings else ''

    if outcome is Outcome.FINISHED:
        if written:
            return Summary(outcome, f'Done: {sorted_lists} sorted', f'Done in {duration}: {sorted_lists} sorted'
                           f'{warnings}.', '🎉', written)
        return Summary(outcome, 'Done: nothing new to sort', f'Done in {duration}: nothing new to sort{warnings}.',
                       '✅', written)
    if outcome is Outcome.ERRORS:
        return Summary(outcome, 'Finished with errors', f'Finished with errors in {duration} (see the messages '
                       f'above): {sorted_lists} sorted.', '❌', written)
    if outcome is Outcome.STOPPED:
        already = f' {sorted_lists.capitalize()} already sorted.' if written else ''
        return Summary(outcome, 'Stopped', f'Stopped after {duration}.{already}', '🛑', written)
    return Summary(outcome, 'Failed', f'Failed after {duration} (see the messages above).', '❌', written)
