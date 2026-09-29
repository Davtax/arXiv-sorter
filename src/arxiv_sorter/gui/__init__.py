"""
Graphical interface of arXiv-sorter, built with PySide6.
"""
import sys

from arxiv_sorter.protocol import SCHEDULED_FLAG, WORKER_FLAG


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == WORKER_FLAG:
        # The GUI binary started itself to run the command line program (see gui.window.worker_command)
        from arxiv_sorter.cli import main as cli_main

        cli_main(sys.argv[2:])
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == SCHEDULED_FLAG:
        # Daily run started by the operating system (see arxiv_sorter.scheduler): no window, only a notification
        from arxiv_sorter.gui.background import run_scheduled

        return run_scheduled()

    from arxiv_sorter.gui.window import start_gui  # Qt is only imported when the window is needed

    return start_gui()
