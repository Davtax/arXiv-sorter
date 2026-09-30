"""
Check that the GUI binary works: it runs the command line program, and the window starts without crashing (using the
offscreen platform of Qt, since the CI runners have no display).

Usage: python scripts/smoke_test_gui.py <path to the GUI executable>
"""
import os
import subprocess
import sys
import time

from arxorter.system import kill_process_tree

T_ALIVE = 15  # seconds the window must keep running


def main(executable: str) -> int:
    worker = subprocess.run([executable, '--worker', '--version'], capture_output=True, text=True, timeout=120)
    print(f'Worker output: {worker.stdout.strip()!r} (exit code {worker.returncode})')
    if worker.returncode != 0 or 'arxorter' not in worker.stdout:
        print(worker.stderr)
        return 1

    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    window = subprocess.Popen([executable], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(T_ALIVE)
    alive = window.poll() is None
    kill_process_tree(window.pid)  # A single file binary runs as two processes
    output = window.communicate()[0].decode(errors='replace')

    print(f'Window running after {T_ALIVE} s: {alive}')
    if not alive:
        print(f'Exit code {window.returncode}, output:\n{output}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
