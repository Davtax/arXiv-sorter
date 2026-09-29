"""
Communication between the GUI and the arXiv-sorter process it runs. Kept free of dependencies, so importing it does not
load Qt in the worker process nor gevent in the GUI.
"""
import os

WORKER_FLAG = '--worker'  # Makes the GUI launcher run the command line program instead (see arxiv_sorter.gui.main)
GUI_ENV_VAR = 'ARXIV_SORTER_GUI'

# Progress bars, questions and written files are sent to the GUI as tagged lines through the standard output
PROGRESS_TAG = '@@arxiv-sorter:progress@@'
QUESTION_TAG = '@@arxiv-sorter:question@@'
WRITTEN_TAG = '@@arxiv-sorter:written@@'


def gui_mode() -> bool:
    return os.environ.get(GUI_ENV_VAR) == '1'
