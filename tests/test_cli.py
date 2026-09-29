import pytest

from arxiv_sorter import cli


@pytest.fixture
def four_cpus(monkeypatch):
    monkeypatch.setattr(cli, 'max_threads', lambda: 4)


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
