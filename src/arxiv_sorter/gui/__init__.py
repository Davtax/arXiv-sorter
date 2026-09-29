"""
Graphical interface of arXiv-sorter, built with PySide6.
"""
import sys

from arxiv_sorter.protocol import WORKER_FLAG


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == WORKER_FLAG:
        # The GUI binary started itself to run the command line program (see gui.window.worker_command)
        from arxiv_sorter.cli import main as cli_main

        cli_main(sys.argv[2:])
        return 0

    from arxiv_sorter.gui.window import start_gui  # Qt is only imported when the window is needed

    return start_gui()
