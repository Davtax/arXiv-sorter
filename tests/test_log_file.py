import pytest

from arxorter import cli, console, log_file


def test_messages_and_details_are_logged(capsys):
    path = log_file.start_log_file(['-d', 'searches'])

    console.info('103 entries', icon='📄')
    console.detail('Only with --verbose on screen')
    console.error('Broken')

    text = path.read_text(encoding='utf-8')
    assert 'Arguments: -d searches' in text
    assert 'INFO     103 entries' in text
    assert 'DEBUG    Only with --verbose on screen' in text  # Kept in the file, although not printed
    assert 'ERROR    Broken' in text
    assert 'Only with --verbose' not in capsys.readouterr().out


def test_only_the_last_runs_are_kept(tmp_path, monkeypatch):
    logs = tmp_path / 'logs'
    logs.mkdir()
    for day in range(1, log_file.KEEP + 6):
        (logs / f'2026-08-{day:02} 10-00-00.log').write_text('old', encoding='utf-8')

    path = log_file.start_log_file([])

    files = log_file.log_files()
    assert len(files) == log_file.KEEP
    assert files[-1] == path == log_file.latest_log()
    assert not (logs / '2026-08-01 10-00-00.log').exists()


def test_no_log_file_if_the_folder_cannot_be_written(tmp_path, monkeypatch):
    blocker = tmp_path / 'file'
    blocker.write_text('not a folder', encoding='utf-8')
    monkeypatch.setattr(log_file, 'logs_dir', lambda: blocker / 'logs')

    assert log_file.start_log_file([]) is None
    console.info('the run goes on')  # No error without the log file


def test_errors_are_logged_with_their_traceback(monkeypatch, capsys):
    def broken(args, temp_dir):
        raise ValueError('something broke')

    monkeypatch.setattr(cli, 'run', broken)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(['-e', '-d', 'x'])

    assert exit_info.value.code == 1
    text = log_file.latest_log().read_text(encoding='utf-8')
    assert 'An error occurred: something broke' in text
    assert 'Traceback (most recent call last)' in text and 'ValueError: something broke' in text
    assert 'The details are in the log file' in capsys.readouterr().out
