"""
Command line interface of arXiv-sorter.
"""
import argparse
import sys
import tempfile
import traceback
from datetime import datetime

from arxiv_sorter import __version__, console
from arxiv_sorter.console import configure_stdout
from arxiv_sorter.log_file import start_log_file
from arxiv_sorter.pipeline import SearchFilesError, run
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


def date_type(value: str) -> str:
    """
    Date in the format YYYYMMDD, kept as text.
    """
    try:
        datetime.strptime(value, '%Y%m%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f'invalid date {value!r}, the format is YYYYMMDD (e.g. 20260818)') from None
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='arxiv-sorter',
        description='Download, sort and highlight the daily arXiv submissions matching your keywords and authors.',
        epilog='More information in https://github.com/Davtax/arXiv-sorter#readme',
    )

    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('-v', '--verbose', action='store_true', help='show detailed messages')

    parser.add_argument('-d', '--directory', default='./',
                        help='folder with keywords.txt, authors.txt and categories.txt (default: current folder)')
    parser.add_argument('-a', '--abstracts', default='./abstracts/',
                        help='folder where the Markdown files are saved (default: ./abstracts)')

    parser.add_argument('-f', '--final', action='store_false', help='do not add a timestamp at the end of the files')
    parser.add_argument('-u', '--update', action='store_true', help='download new versions of arXiv-sorter')
    parser.add_argument('-i', '--image', action='store_false', help='do not include the figures (faster)')
    parser.add_argument('-t', '--threads', type=threads_type, default=1,
                        help=f'threads to detect the figures, from 1 (default) to {max_threads()} in this system. More '
                             'threads are faster, but use more memory')
    parser.add_argument('-s', '--separate', action='store_true', help='create a separate file for each submission')
    parser.add_argument('-m', '--modify', action='store_false',
                        help='do not modify authors.txt (it is sorted and its blank lines removed by default)')
    parser.add_argument('-e', '--exit', action='store_true', help='exit at the end, without waiting for Enter')

    parser.add_argument('--date0', type=date_type, default=None,
                        help='first mailing list to request, as YYYYMMDD (default: after the last one saved)')
    parser.add_argument('--datef', type=date_type, default=None,
                        help='request the submissions until this date, as YYYYMMDD (default: today)')

    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    """
    Run arXiv-sorter with the given command line arguments (sys.argv if None).
    """
    args = parse_args(argv)
    configure_stdout()
    console.set_verbose(args.verbose)
    log_path = start_log_file(sys.argv[1:] if argv is None else argv)
    if log_path is not None:
        console.detail(f'Log file: {log_path}')

    exit_code = 0
    temp_dir = tempfile.TemporaryDirectory()
    try:  # Catch potential errors
        run(args, temp_dir)
        if not console.GUI_MODE:  # The GUI shows its own summary
            console.step('All done', icon='🎉')
    except KeyboardInterrupt:
        console.warning('Stopped by the user', icon='🛑')
        exit_code = 130
    except SearchFilesError as e:  # The mistakes are already listed, with their file and line
        console.error(str(e))
        exit_code = 1
    except Exception as e:
        console.error(f'An error occurred: {e}')
        console.detail(traceback.format_exc().rstrip())  # Always in the log file, on screen with --verbose
        if not args.verbose:
            where = f'in the log file {log_path}, or ' if log_path is not None else ''
            console.info(f'The details are {where}shown with --verbose (or "Show detailed messages" in the window)',
                         icon='💡')
        exit_code = 1
    finally:
        temp_dir.cleanup()

    if not args.exit:
        input('Press Enter to exit …')
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
