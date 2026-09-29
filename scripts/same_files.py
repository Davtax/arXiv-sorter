"""
Check that the Markdown files written on each system have the same lines (used by the build workflow).

Usage: python scripts/same_files.py <file> <file> [<file> ...]
"""
import sys
from pathlib import Path


def main(names: list[str]) -> int:
    missing = [name for name in names if not Path(name).is_file()]
    if missing:
        print(f'Missing files: {", ".join(missing)}')
        return 1

    contents = sorted((Path(name).read_text(encoding='utf-8').splitlines(keepends=True) for name in names), key=len)
    for shorter, longer in zip(contents, contents[1:], strict=False):
        different = [line for line in shorter if line not in longer]
        if different:
            print(f'The following lines are different between the systems: {different}')
            return 1

    print(f'The {len(names)} files have the same lines')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
