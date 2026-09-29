"""
Command line interface of arXiv-sorter.
"""
import argparse
import tempfile
import traceback

from arxiv_sorter import __version__
from arxiv_sorter.console import configure_stdout
from arxiv_sorter.pipeline import run
from arxiv_sorter.system import max_threads


def threads_type(value: str) -> int:
    """
    Number of threads between 1 and the number of CPUs of the system.
    """
    try:
        threads = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f'invalid number of threads: {value!r}') from None
    if not 1 <= threads <= max_threads():
        raise argparse.ArgumentTypeError(f'the number of threads must be between 1 and {max_threads()} (CPUs of this '
                                         f'system), got {threads}')
    return threads


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='arxiv-sorter',
        description='Download, sort and highlight the daily arXiv submissions matching your keywords and authors.',
    )

    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase output verbosity')

    parser.add_argument('-d', '--directory', help='Specify relative keywords directory (default = ./)', default='./')
    parser.add_argument('-a', '--abstracts', help='Specify abstracts directory (default = ./abstracts)',
                        default='./abstracts/')

    parser.add_argument('-f', '--final', action='store_false', help='Remove final date string in MarkDown file')
    parser.add_argument('-u', '--update', action='store_true', help='Update arXiv-sorter')
    parser.add_argument('-i', '--image', action='store_false', help='Remove images from abstracts')
    parser.add_argument('-s', '--separate', action='store_true', help='Separate each entry in a different file')
    parser.add_argument('-m', '--modify', action='store_false',
                        help='Dont modify the authors file (sort and remove blank lines)')
    parser.add_argument('-t', '--threads', type=threads_type, default=1,
                        help=f'Threads to detect the figures, from 1 (default) to {max_threads()} in this system. More '
                             'threads are faster, but use more memory')
    parser.add_argument('-e', '--exit', action='store_true', help='Exit the program, without asking to press enter')

    parser.add_argument('--date0', help='Specify initial date (YYYYMMDD), e.g. 20260818', default=None)
    parser.add_argument('--datef', help='Specify final date (YYYYMMDD), e.g. 20260818', default=None)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    """
    Run arXiv-sorter with the given command line arguments (sys.argv if None).
    """
    args = parse_args(argv)
    configure_stdout()

    temp_dir = tempfile.TemporaryDirectory()
    try:  # Catch potential errors
        run(args, temp_dir)
    except Exception as e:
        print(f'An error occurred: {e}')
        if args.verbose:
            traceback.print_exc()
    finally:
        temp_dir.cleanup()

    if not args.exit:
        input('Press Enter to exit...')


if __name__ == '__main__':
    main()
