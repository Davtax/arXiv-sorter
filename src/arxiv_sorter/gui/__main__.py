import sys

from arxiv_sorter.gui import main

if __name__ == '__main__':  # Not when the processes that extract the figures import it
    sys.exit(main())
