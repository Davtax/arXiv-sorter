"""
Dialog to run arXiv-sorter every day in the background, change the time, or stop it (see arxiv_sorter.scheduler).
"""
from datetime import time

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTimeEdit, QVBoxLayout, QWidget

DEFAULT_TIME = time(9, 0)

EXPLANATION = (
    'arXiv-sorter runs without opening its window, with the folders and options of this window (from the last mailing '
    'list saved, whatever the date range), and shows a notification when it finishes. If the computer is off or '
    'asleep at that time, it runs as soon as possible.'
)


def describe_schedule(at: time | None) -> str:
    return f'Daily at {at:%H:%M}' if at is not None else 'Not scheduled'


class ScheduleDialog(QDialog):
    def __init__(self, current: time | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle('Daily run')

        self.enabled_check = QCheckBox('Run arXiv-sorter every day at')
        self.enabled_check.setChecked(current is not None)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat('HH:mm')
        chosen = current or DEFAULT_TIME
        self.time_edit.setTime(QTime(chosen.hour, chosen.minute))
        self.time_edit.setEnabled(current is not None)
        self.enabled_check.toggled.connect(self.time_edit.setEnabled)

        row = QHBoxLayout()
        row.addWidget(self.enabled_check)
        row.addWidget(self.time_edit)
        row.addStretch()

        explanation = QLabel(EXPLANATION)
        explanation.setWordWrap(True)
        explanation.setEnabled(False)  # Secondary text

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(explanation)
        layout.addWidget(buttons)
        self.setMinimumWidth(460)

    def chosen_time(self) -> time | None:
        """
        Time of the daily run, or None to remove it.
        """
        if not self.enabled_check.isChecked():
            return None
        chosen = self.time_edit.time()
        return time(chosen.hour(), chosen.minute())
