"""
Daily run of arXorter in the background, registered in the scheduler of the operating system: the Task Scheduler on
Windows, a launchd agent on macOS and a systemd user timer on Linux. The scheduled program is the GUI binary with
--scheduled (see arxorter.gui.background), which runs with the settings saved by the window, without showing it.

The operating system keeps the schedule, so there is nothing to keep in sync: the time is read back from it. A run
missed because the computer was off or asleep starts as soon as possible (on macOS, only after sleeping).
"""
import os
import plistlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from xml.sax.saxutils import escape

from arxorter.protocol import SCHEDULED_FLAG
from arxorter.system import APP_NAME, NO_WINDOW, base_dir, is_frozen

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # Folder that contains the arxorter package

WINDOWS_TASK = f'{APP_NAME} daily run'
LAUNCHD_LABEL = 'io.github.davtax.arxorter.daily'
SYSTEMD_UNIT = 'arxorter-daily'
TIME_LIMIT_HOURS = 2  # A run that takes longer is stopped (it is stuck, e.g. waiting for the network)


class SchedulerError(Exception):
    """
    The operating system refused to create, read or remove the scheduled run.
    """


@dataclass
class Command:
    """
    Program started by the scheduler.
    """
    program: str
    arguments: list[str]
    working_dir: str


def background_command() -> Command:
    """
    The GUI program in background mode: the binary itself, or the Python interpreter (without console on Windows) with
    the package importable from the working directory, even if it is not installed.
    """
    if is_frozen():
        if 'AppTranslocation' in Path(sys.executable).parts:
            # macOS runs a quarantined app from a random folder, removed when it quits: the daily run would not find it
            raise SchedulerError('macOS runs arXorter from a temporary copy, since it was downloaded with a '
                                 'browser. Move the app to another folder with the Finder (or run xattr -dr '
                                 'com.apple.quarantine on it), open it again and then choose the daily run.')
        return Command(sys.executable, [SCHEDULED_FLAG], str(base_dir()))

    python = Path(sys.executable)
    pythonw = python.with_name('pythonw.exe')
    if os.name == 'nt' and pythonw.is_file():
        python = pythonw
    return Command(str(python), ['-m', 'arxorter.gui', SCHEDULED_FLAG], str(PACKAGE_ROOT))


# --------------------------------------------------------------------- public interface
def scheduled_time() -> time | None:
    """
    Time of the daily run, or None if it is not scheduled.
    """
    if sys.platform == 'win32':
        return _windows_time()
    if sys.platform == 'darwin':
        return _launchd_time()
    return _systemd_time()


def schedule(at: time, command: Command | None = None):
    """
    Run arXorter every day at the given time, replacing the previous schedule.
    """
    command = command or background_command()
    if sys.platform == 'win32':
        _windows_schedule(at, command)
    elif sys.platform == 'darwin':
        _launchd_schedule(at, command)
    else:
        _systemd_schedule(at, command)


def follow_program():
    """
    Update the daily run when the app was moved since it was scheduled (macOS), so it does not start a program that is
    no longer there. It is called when the window opens: the app is found again where it is now. From Python, the
    program is the interpreter, which does not move.
    """
    if sys.platform != 'darwin' or not is_frozen():
        return  # The Windows task and the systemd service keep the path too, but are not checked yet
    at = _launchd_time()
    if at is None:
        return
    try:
        command = background_command()
    except SchedulerError:
        return  # Translocated copy: keep the agent of the program in its real folder
    if _launchd_arguments() != [command.program, *command.arguments]:
        _launchd_schedule(at, command)


def unschedule():
    """
    Remove the daily run, if there is one.
    """
    if sys.platform == 'win32':
        _windows_unschedule()
    elif sys.platform == 'darwin':
        _launchd_unschedule()
    else:
        _systemd_unschedule()


def _run(arguments: list[str], check: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW)
    except OSError as error:
        raise SchedulerError(f'Unable to run {arguments[0]}: {error}') from None
    if check and result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        raise SchedulerError(f'{arguments[0]} failed: {output or f"exit code {result.returncode}"}')
    return result


# ---------------------------------------------------------------------------- Windows
def windows_task_xml(at: time, command: Command, user: str = '') -> str:
    """
    Definition of the task: every day at the given time, as the current user and only while they are logged in (so
    the notification can be shown), also on battery, and as soon as possible when the time was missed.
    """
    start = datetime.combine(date.today(), at.replace(second=0, microsecond=0)).isoformat()
    user_id = f'<UserId>{escape(user)}</UserId>' if user else ''
    arguments = subprocess.list2cmdline(command.arguments)
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Sort the new arXiv submissions every day, in the background. Created by {APP_NAME}; change or remove \
it from the program.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      {user_id}
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT{TIME_LIMIT_HOURS}H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command.program)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(command.working_dir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
'''


def parse_windows_time(task_xml: str) -> time | None:
    match = re.search(r'<StartBoundary>[^<]*T(\d{2}):(\d{2})', task_xml)
    return time(int(match[1]), int(match[2])) if match else None


def _windows_user() -> str:
    user, domain = os.environ.get('USERNAME', ''), os.environ.get('USERDOMAIN', '')
    return f'{domain}\\{user}' if user and domain else user


def _windows_time() -> time | None:
    result = _run(['schtasks', '/Query', '/TN', WINDOWS_TASK, '/XML'], check=False)
    return parse_windows_time(result.stdout) if result.returncode == 0 else None


def _windows_schedule(at: time, command: Command):
    with tempfile.TemporaryDirectory() as folder:
        definition = Path(folder) / 'task.xml'
        definition.write_text(windows_task_xml(at, command, _windows_user()), encoding='utf-16')
        _run(['schtasks', '/Create', '/TN', WINDOWS_TASK, '/XML', str(definition), '/F'])


def _windows_unschedule():
    if _windows_time() is not None:
        _run(['schtasks', '/Delete', '/TN', WINDOWS_TASK, '/F'])


# ------------------------------------------------------------------------------ macOS
def launchd_plist_path() -> Path:
    return Path.home() / 'Library' / 'LaunchAgents' / f'{LAUNCHD_LABEL}.plist'


def launchd_plist(at: time, command: Command) -> bytes:
    """
    Launch agent run every day at the given time (and when waking up, if the time passed while asleep).
    """
    return plistlib.dumps({
        'Label': LAUNCHD_LABEL,
        'ProgramArguments': [command.program, *command.arguments],
        'WorkingDirectory': command.working_dir,
        'StartCalendarInterval': {'Hour': at.hour, 'Minute': at.minute},
        'ProcessType': 'Background',
    })


def parse_launchd_time(content: bytes) -> time | None:
    try:
        interval = plistlib.loads(content)['StartCalendarInterval']
        return time(interval['Hour'], interval['Minute'])
    except (plistlib.InvalidFileException, ValueError, KeyError, TypeError):
        return None


def _launchd_arguments() -> list[str] | None:
    try:
        return plistlib.loads(launchd_plist_path().read_bytes())['ProgramArguments']
    except (OSError, plistlib.InvalidFileException, ValueError, KeyError, TypeError):
        return None


def _launchd_domain() -> str:
    return f'gui/{os.getuid()}'  # type: ignore[attr-defined, unused-ignore]  # Not on Windows (nor used)


def _launchd_time() -> time | None:
    try:
        return parse_launchd_time(launchd_plist_path().read_bytes())
    except OSError:
        return None


def _launchd_schedule(at: time, command: Command):
    path = launchd_plist_path()
    _launchd_unschedule()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(launchd_plist(at, command))
    except OSError as error:
        raise SchedulerError(f'Unable to write {path}: {error}') from None
    _run(['launchctl', 'bootstrap', _launchd_domain(), str(path)])


def _launchd_unschedule():
    path = launchd_plist_path()
    if path.exists():
        _run(['launchctl', 'bootout', f'{_launchd_domain()}/{LAUNCHD_LABEL}'], check=False)  # Not loaded
        path.unlink(missing_ok=True)


# ------------------------------------------------------------------------------ Linux
def systemd_dir() -> Path:
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'systemd' / 'user'


def _systemd_quote(argument: str) -> str:
    argument = argument.replace('%', '%%')  # Specifiers of systemd
    if re.fullmatch(r'[\w/.:=+-]+', argument):
        return argument
    return '"' + argument.replace('\\', '\\\\').replace('"', '\\"') + '"'


def systemd_units(at: time, command: Command) -> dict[str, str]:
    """
    Service that runs arXorter once, and timer that starts it every day at the given time (or as soon as possible,
    if the computer was off).
    """
    exec_start = ' '.join(_systemd_quote(argument) for argument in [command.program, *command.arguments])
    service = f'''[Unit]
Description={APP_NAME} daily run

[Service]
Type=oneshot
WorkingDirectory={_systemd_quote(command.working_dir)}
ExecStart={exec_start}
TimeoutStartSec={TIME_LIMIT_HOURS}h
'''
    timer = f'''[Unit]
Description={APP_NAME} daily run, created by {APP_NAME} (change or remove it from the program)

[Timer]
OnCalendar=*-*-* {at:%H:%M}:00
Persistent=true

[Install]
WantedBy=timers.target
'''
    return {f'{SYSTEMD_UNIT}.service': service, f'{SYSTEMD_UNIT}.timer': timer}


def parse_systemd_time(timer: str) -> time | None:
    match = re.search(r'^OnCalendar=\*-\*-\* (\d{2}):(\d{2})', timer, re.MULTILINE)
    return time(int(match[1]), int(match[2])) if match else None


def _systemd_time() -> time | None:
    try:
        return parse_systemd_time((systemd_dir() / f'{SYSTEMD_UNIT}.timer').read_text(encoding='utf-8'))
    except OSError:
        return None


def _systemd_schedule(at: time, command: Command):
    folder = systemd_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in systemd_units(at, command).items():
            (folder / name).write_text(content, encoding='utf-8')
    except OSError as error:
        raise SchedulerError(f'Unable to write the systemd units in {folder}: {error}') from None
    _run(['systemctl', '--user', 'daemon-reload'])
    _run(['systemctl', '--user', 'enable', '--now', f'{SYSTEMD_UNIT}.timer'])
    _run(['systemctl', '--user', 'restart', f'{SYSTEMD_UNIT}.timer'])  # Already enabled: take the new time


def _systemd_unschedule():
    folder = systemd_dir()
    if not (folder / f'{SYSTEMD_UNIT}.timer').exists():
        return
    _run(['systemctl', '--user', 'disable', '--now', f'{SYSTEMD_UNIT}.timer'], check=False)
    for name in (f'{SYSTEMD_UNIT}.timer', f'{SYSTEMD_UNIT}.service'):
        (folder / name).unlink(missing_ok=True)
    _run(['systemctl', '--user', 'daemon-reload'], check=False)
