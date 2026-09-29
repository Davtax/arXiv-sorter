"""
Platform dependent details, shared by the command line program and the GUI.
"""
import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path

# creationflags of subprocess, so console programs (java, curl) do not open a terminal window on Windows (0 elsewhere)
if sys.platform == 'win32':
    NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    NO_WINDOW = 0


APP_NAME = 'arXiv-sorter'


def config_dir() -> Path:
    """
    Folder of the user configuration, which persists between runs and updates of the program: the GUI settings, the
    pdffigures2 jar and the Java runtime. It is the same folder as QStandardPaths.AppConfigLocation for the GUI,
    computed without Qt so the command line program can use it too.
    """
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Preferences'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / APP_NAME


def max_threads() -> int:
    """
    Maximum number of threads to detect the figures: the number of logical CPUs of the system.
    """
    return os.cpu_count() or 1


def is_frozen() -> bool:
    """
    Whether the program runs as a binary built with PyInstaller.
    """
    return getattr(sys, 'frozen', False)


def installed_path() -> Path:
    """
    The installed program, which an update replaces: the .app bundle on macOS, the binary elsewhere.
    """
    executable = Path(sys.executable).resolve()
    return next((parent for parent in executable.parents if parent.suffix == '.app'), executable)


def base_dir() -> Path:
    """
    Directory where the user files are by default: next to the binary, or the current directory when run from Python.

    A macOS app is a bundle (arXiv-sorter-GUI-macOS.app/Contents/MacOS/arXiv-sorter-GUI-macOS), which must not be
    modified, so the folder that contains the bundle is used instead. When macOS runs a quarantined app from a random
    read-only location (App Translocation), or that folder is not writable, ~/arXiv-sorter is used.
    """
    if not is_frozen():
        return Path.cwd()

    installed = installed_path()
    if installed.suffix != '.app':
        return installed.parent

    folder = installed.parent
    if 'AppTranslocation' not in folder.parts and os.access(folder, os.W_OK):
        return folder

    fallback = Path.home() / 'arXiv-sorter'
    fallback.mkdir(exist_ok=True)
    return fallback


def descendant_pids(pid: int) -> list[int]:
    """
    Processes started by the given one, directly or not (macOS and Linux).
    """
    try:
        result = subprocess.run(['pgrep', '-P', str(pid)], capture_output=True, text=True)
    except OSError:  # pgrep is not available
        return []

    children = [int(child) for child in result.stdout.split()]
    return children + [descendant for child in children for descendant in descendant_pids(child)]


def kill_process_tree(pid: int):
    """
    Kill the process together with the programs it started (e.g. java), which would keep running otherwise.
    """
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)], capture_output=True, creationflags=NO_WINDOW)
        return

    for process_id in [pid, *descendant_pids(pid)]:  # Collected before killing, since orphans are adopted by init
        with contextlib.suppress(OSError):  # Already finished
            os.kill(process_id, signal.SIGKILL)
