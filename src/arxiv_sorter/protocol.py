"""
Communication between the GUI and the arXiv-sorter process it runs. Kept free of dependencies, so importing it does not
load Qt in the worker process nor gevent in the GUI.
"""
import os
from enum import StrEnum

WORKER_FLAG = '--worker'  # Makes the GUI launcher run the command line program instead (see arxiv_sorter.gui.main)
SCHEDULED_FLAG = '--scheduled'  # Makes the GUI launcher run in the background (see arxiv_sorter.scheduler)
GUI_ENV_VAR = 'ARXIV_SORTER_GUI'
BUSY_EXIT_CODE = 75  # Another run is in progress (EX_TEMPFAIL), see arxiv_sorter.run_lock

# Messages, progress bars, questions and written files are sent to the GUI as tagged lines through the standard output
LOG_TAG = '@@arxiv-sorter:log@@'
PROGRESS_TAG = '@@arxiv-sorter:progress@@'
QUESTION_TAG = '@@arxiv-sorter:question@@'
WRITTEN_TAG = '@@arxiv-sorter:written@@'


class Level(StrEnum):
    """
    Kind of message, which sets how it is shown (color, icon, and whether it is shown at all).
    """
    STEP = 'step'  # Start of a new stage of the run, shown as a heading
    INFO = 'info'
    SUCCESS = 'success'
    WARNING = 'warning'  # Something went wrong, but the run goes on
    ERROR = 'error'  # The run could not finish
    DETAIL = 'detail'  # Only shown with --verbose


def gui_mode() -> bool:
    return os.environ.get(GUI_ENV_VAR) == '1'
