"""
Launcher of the GUI, used to build the binary with PyInstaller. Equivalent to `arxiv-sorter-gui`.
"""
import multiprocessing
import sys

from arxiv_sorter.gui import main

if __name__ == '__main__':
    # The binary also runs the processes that extract the figures, started with --multiprocessing-fork
    multiprocessing.freeze_support()
    sys.exit(main())
