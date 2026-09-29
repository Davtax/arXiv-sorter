"""
Launcher of the command line program, used to build the binary with PyInstaller. Equivalent to `arxiv-sorter`.
"""
import multiprocessing

from arxiv_sorter.cli import main

if __name__ == '__main__':
    # The binary also runs the processes that extract the figures, started with --multiprocessing-fork
    multiprocessing.freeze_support()
    main()
