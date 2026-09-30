"""
Launcher of the GUI, used to build the binary with PyInstaller. Equivalent to `arxorter-gui`.
"""
import multiprocessing
import sys

from arxorter.gui import main

if __name__ == '__main__':
    # The binary also runs the processes that extract the figures, started with --multiprocessing-fork
    multiprocessing.freeze_support()
    sys.exit(main())
