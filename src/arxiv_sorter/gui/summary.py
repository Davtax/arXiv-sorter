"""
Final message shown in the GUI when a run ends.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

SEPARATOR = '─' * 60


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


def format_duration(seconds: float) -> str:
    minutes, seconds = divmod(round(seconds), 60)
    return f'{minutes} min {seconds:02} s' if minutes else f'{seconds} s'


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f'{count} {singular}' if count == 1 else f'{count} {plural or singular + "s"}'


def final_message(outcome: Outcome, elapsed: float, written: list[WrittenFile]) -> tuple[str, list[str]]:
    """
    Short status and the lines of the final message.
    """
    duration = format_duration(elapsed)
    sorted_lists = _plural(len(written), 'mailing list')

    if outcome is Outcome.FINISHED:
        status = f'Done: {sorted_lists} sorted' if written else 'Done: nothing new to sort'
        headline = f'Done in {duration}: {sorted_lists} sorted.' if written else f'Done in {duration}: nothing new.'
    elif outcome is Outcome.ERRORS:
        status = 'Finished with errors'
        headline = f'Finished with errors in {duration} (see the messages above): {sorted_lists} sorted.'
    elif outcome is Outcome.STOPPED:
        status = 'Stopped'
        headline = f'Stopped after {duration}.' + (f' {sorted_lists.capitalize()} already sorted.' if written else '')
    else:
        status = 'Failed'
        headline = f'Failed after {duration} (see the messages above).'

    lines = [SEPARATOR, headline]
    if written:
        width = max(len(file.path.name) for file in written)
        for file in written:
            entries = _plural(file.n_entries, 'entry', 'entries')
            lines.append(f'  {file.path.name:<{width}}  {entries}, {file.n_new} new or with matching keywords')
        folders = {file.path.parent for file in written}
        lines.append(f'Saved in {folders.pop()}' if len(folders) == 1 else 'Saved in several folders')
    lines.append(SEPARATOR)

    return status, lines
