import plistlib
import sys
from datetime import time

import pytest

from arxorter import scheduler
from arxorter.protocol import SCHEDULED_FLAG
from arxorter.scheduler import Command

COMMAND = Command('C:/Program Files/arXorter/arXorter-GUI.exe', [SCHEDULED_FLAG, 'a & b'], 'C:/My <folder>')


class TestWindows:
    def test_the_task_runs_every_day_at_the_time(self):
        xml = scheduler.windows_task_xml(time(7, 5), COMMAND, 'DOMAIN\\user')
        assert scheduler.parse_windows_time(xml) == time(7, 5)
        assert '<DaysInterval>1</DaysInterval>' in xml
        assert '<StartWhenAvailable>true</StartWhenAvailable>' in xml
        assert '<UserId>DOMAIN\\user</UserId>' in xml

    def test_the_command_is_escaped(self):
        xml = scheduler.windows_task_xml(time(7, 5), COMMAND)
        assert '<Command>C:/Program Files/arXorter/arXorter-GUI.exe</Command>' in xml
        assert f'<Arguments>{SCHEDULED_FLAG} "a &amp; b"</Arguments>' in xml
        assert '<WorkingDirectory>C:/My &lt;folder&gt;</WorkingDirectory>' in xml
        assert '<UserId>' not in xml

    def test_a_task_without_start_has_no_time(self):
        assert scheduler.parse_windows_time('<Task></Task>') is None


class TestMacOS:
    def test_the_agent_runs_every_day_at_the_time(self):
        content = scheduler.launchd_plist(time(21, 30), COMMAND)
        assert scheduler.parse_launchd_time(content) == time(21, 30)
        agent = plistlib.loads(content)
        assert agent['ProgramArguments'] == [COMMAND.program, *COMMAND.arguments]
        assert agent['WorkingDirectory'] == COMMAND.working_dir

    @pytest.mark.parametrize('content', [b'', b'not a plist', plistlib.dumps({'Label': 'x'})])
    def test_invalid_agents_have_no_time(self, content):
        assert scheduler.parse_launchd_time(content) is None

    def test_the_time_is_read_from_the_agent(self, tmp_path, monkeypatch):
        path = tmp_path / 'agent.plist'
        monkeypatch.setattr(scheduler, 'launchd_plist_path', lambda: path)
        assert scheduler._launchd_time() is None
        path.write_bytes(scheduler.launchd_plist(time(6, 0), COMMAND))
        assert scheduler._launchd_time() == time(6, 0)

    def test_a_moved_app_is_scheduled_again_where_it_is_now(self, tmp_path, monkeypatch):
        path = tmp_path / 'agent.plist'
        path.write_bytes(scheduler.launchd_plist(time(6, 0), Command('/old/place/arXorter', [SCHEDULED_FLAG], '/')))
        now = Command('/new/place/arXorter', [SCHEDULED_FLAG], '/new')
        rescheduled = []
        monkeypatch.setattr(sys, 'platform', 'darwin')
        monkeypatch.setattr(sys, 'frozen', True, raising=False)
        monkeypatch.setattr(scheduler, 'launchd_plist_path', lambda: path)
        monkeypatch.setattr(scheduler, 'background_command', lambda: now)
        monkeypatch.setattr(scheduler, '_launchd_schedule', lambda at, command: rescheduled.append((at, command)))

        scheduler.follow_program()
        assert rescheduled == [(time(6, 0), now)]

        path.write_bytes(scheduler.launchd_plist(time(6, 0), now))
        scheduler.follow_program()
        assert len(rescheduled) == 1  # Already there

    def test_a_translocated_app_is_not_scheduled(self, monkeypatch):
        monkeypatch.setattr(sys, 'frozen', True, raising=False)
        monkeypatch.setattr(sys, 'executable', '/private/var/folders/x/AppTranslocation/1/d/arXorter-GUI-macOS.app/'
                                               'Contents/MacOS/arXorter')
        with pytest.raises(scheduler.SchedulerError, match='temporary copy'):
            scheduler.background_command()


class TestLinux:
    def test_the_timer_runs_every_day_at_the_time(self):
        units = scheduler.systemd_units(time(8, 0), COMMAND)
        timer = units[f'{scheduler.SYSTEMD_UNIT}.timer']
        assert scheduler.parse_systemd_time(timer) == time(8, 0)
        assert 'Persistent=true' in timer

    def test_the_command_is_quoted(self):
        service = scheduler.systemd_units(time(8, 0), Command('/opt/my programs', ['100%'], '/home/me'))[
            f'{scheduler.SYSTEMD_UNIT}.service']
        assert 'ExecStart="/opt/my programs" "100%%"' in service
        assert 'WorkingDirectory=/home/me' in service

    def test_the_time_is_read_from_the_timer(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scheduler, 'systemd_dir', lambda: tmp_path)
        assert scheduler._systemd_time() is None
        for name, content in scheduler.systemd_units(time(23, 59), COMMAND).items():
            (tmp_path / name).write_text(content, encoding='utf-8')
        assert scheduler._systemd_time() == time(23, 59)


def test_the_background_command_runs_the_gui_in_scheduled_mode():
    command = scheduler.background_command()
    assert command.arguments[-1] == SCHEDULED_FLAG
    assert command.arguments[:2] == ['-m', 'arxorter.gui']  # Not frozen in the tests


def test_failures_of_the_scheduler_are_reported(monkeypatch):
    with pytest.raises(scheduler.SchedulerError, match='Unable to run'):
        scheduler._run(['a-program-that-does-not-exist-arxorter'])

