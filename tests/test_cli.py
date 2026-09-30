import pytest

from arxorter import cli, run_lock
from arxorter.protocol import BUSY_EXIT_CODE


@pytest.fixture
def four_cpus(monkeypatch):
    monkeypatch.setattr(cli, 'max_threads', lambda: 4)


class TestDates:
    def test_valid_dates(self):
        args = cli.parse_args(['--date0', '20260921', '--datef', '20260924'])

        assert (args.date0, args.datef) == ('20260921', '20260924')

    @pytest.mark.parametrize('value', ['2026', '2026-09-21', '20261321', 'today'])
    def test_rejects_invalid_dates(self, capsys, value):
        with pytest.raises(SystemExit):
            cli.parse_args(['--date0', value])

        assert 'the format is YYYYMMDD' in capsys.readouterr().err


class TestThreads:
    def test_one_thread_by_default(self, four_cpus):
        assert cli.parse_args([]).threads == 1

    @pytest.mark.parametrize('value', ['1', '4'])
    def test_accepts_up_to_the_cpus(self, four_cpus, value):
        assert cli.parse_args(['--threads', value]).threads == int(value)

    @pytest.mark.parametrize('value', ['0', '5', '-1', 'two'])
    def test_rejects_invalid_values(self, four_cpus, capsys, value):
        with pytest.raises(SystemExit):
            cli.parse_args(['-t', value])

        assert 'argument -t/--threads' in capsys.readouterr().err

    def test_error_names_the_maximum(self, four_cpus, capsys):
        with pytest.raises(SystemExit):
            cli.parse_args(['-t', '8'])

        assert 'between 1 and 4' in capsys.readouterr().err


class TestLock:
    def test_a_second_run_is_refused(self, tmp_path, capsys):
        with run_lock.RunLock() as lock:
            assert lock.acquire()
            with pytest.raises(SystemExit) as stopped:
                cli.main(['--exit', '--directory', str(tmp_path), '--abstracts', str(tmp_path / 'abstracts')])

        assert stopped.value.code == BUSY_EXIT_CODE
        assert 'already running' in capsys.readouterr().out
        assert not (tmp_path / 'logs').exists()  # No log file for a run that did not start
        assert not (tmp_path / 'abstracts').exists()
