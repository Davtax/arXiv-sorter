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


APP_NAME = 'arXorter'


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


def is_translocated(path: Path) -> bool:
    """
    Whether macOS runs the app from a random read-only location (App Translocation), which it does for a quarantined
    app (e.g. just downloaded) that the user has not moved.
    """
    return 'AppTranslocation' in path.parts


def original_path(path: Path) -> Path:
    """
    Where a translocated app really is (the path the user sees in the Finder), found with the Security framework. The
    path is returned unchanged if it is not translocated, or the original location is not known.
    """
    if sys.platform != 'darwin' or not is_translocated(path):
        return path

    import ctypes  # Only needed here, on macOS

    try:
        core = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        security = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
    except OSError:
        return path

    core.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    core.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long,
                                                             ctypes.c_bool]
    core.CFURLGetFileSystemRepresentation.restype = ctypes.c_bool
    core.CFURLGetFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_char_p, ctypes.c_long]
    core.CFRelease.argtypes = [ctypes.c_void_p]
    security.SecTranslocateCreateOriginalPathForURL.restype = ctypes.c_void_p
    security.SecTranslocateCreateOriginalPathForURL.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    encoded = os.fsencode(path)
    url = core.CFURLCreateFromFileSystemRepresentation(None, encoded, len(encoded), path.is_dir())
    if not url:
        return path
    original = security.SecTranslocateCreateOriginalPathForURL(url, None)
    core.CFRelease(url)
    if not original:
        return path

    buffer = ctypes.create_string_buffer(4096)
    found = core.CFURLGetFileSystemRepresentation(original, True, buffer, len(buffer))
    core.CFRelease(original)
    return Path(os.fsdecode(buffer.value)) if found else path


def base_dir() -> Path:
    """
    Directory where the user files are by default: next to the binary, or the current directory when run from Python.

    A macOS app is a bundle (arXorter-GUI-macOS.app/Contents/MacOS/arXorter), which must not be
    modified, so the folder that contains the bundle is used instead. When macOS runs a quarantined app from a random
    read-only location (App Translocation), or that folder is not writable, ~/arXorter is used.
    """
    if not is_frozen():
        return Path.cwd()

    installed = installed_path()
    if installed.suffix != '.app':
        return installed.parent

    folder = installed.parent
    if not is_translocated(folder) and os.access(folder, os.W_OK):
        return folder

    fallback = Path.home() / APP_NAME
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
