import tempfile
import argparse

from app.main import main

temp_dir = tempfile.TemporaryDirectory()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

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
    parser.add_argument('-e', '--exit', action='store_true', help='Exit the program, without asking to press enter')

    parser.add_argument('--date0', help='Specify initial date (%Y%M%D)', default=None)
    parser.add_argument('--datef', help='Specify final date (%Y%M%D)', default=None)

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()

    try:  # Catch potential errors
        main(args, temp_dir)
    except Exception as e:
        print(f'An error occurred: {e}')

    temp_dir.cleanup()

    if not args.exit:
        input('Press Enter to exit...')
