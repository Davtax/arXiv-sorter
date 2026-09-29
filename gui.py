"""
Launcher of the GUI, used to build the binary with PyInstaller. Equivalent to `arxiv-sorter-gui`.
"""
import sys

from arxiv_sorter.gui import main

if __name__ == '__main__':
    sys.exit(main())
