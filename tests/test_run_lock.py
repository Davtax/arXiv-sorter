import subprocess
import sys

from arxorter.run_lock import RunLock, is_running


def test_only_one_run_holds_the_lock(tmp_path):
    path = tmp_path / 'run.lock'
    first = RunLock(path)
    assert first.acquire()
    assert first.acquire()  # Already held by this run
    assert not RunLock(path).acquire()
    assert is_running(path)

    first.release()
    assert not is_running(path)
    assert RunLock(path).acquire()


def test_the_lock_is_seen_by_other_processes(tmp_path):
    path = tmp_path / 'run.lock'
    code = ('from pathlib import Path; from arxorter.run_lock import is_running; '
            f'print(is_running(Path({str(path)!r})))')

    def other_process_sees_a_run() -> bool:
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
        return result.stdout.strip() == 'True'

    with RunLock(path) as lock:
        assert lock.acquire()
        assert other_process_sees_a_run()
    assert not other_process_sees_a_run()

