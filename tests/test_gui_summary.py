from pathlib import Path

import pytest

from arxiv_sorter.gui.summary import SEPARATOR, Outcome, WrittenFile, final_message, format_duration

WRITTEN = [
    WrittenFile(Path('abstracts') / '2026-09-22.md', 103, 101),
    WrittenFile(Path('abstracts') / '2026-09-23.md', 1, 1),
]


@pytest.mark.parametrize(('seconds', 'expected'),
                         [(0.4, '0 s'), (42, '42 s'), (65.2, '1 min 05 s'), (600, '10 min 00 s')])
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


class TestWrittenFile:
    def test_parses_message_with_spaces_in_the_path(self):
        written = WrittenFile.from_message('103\t101\tMy abstracts/2026-09-22.md')

        assert written == WrittenFile(Path('My abstracts') / '2026-09-22.md', 103, 101)

    @pytest.mark.parametrize('message', ['', 'garbage', 'x\ty\tpath'])
    def test_invalid_message(self, message):
        assert WrittenFile.from_message(message) is None


class TestFinalMessage:
    def test_finished_lists_the_files(self):
        status, lines = final_message(Outcome.FINISHED, 65, WRITTEN)

        assert status == 'Done: 2 mailing lists sorted'
        assert lines[0] == lines[-1] == SEPARATOR
        assert lines[1] == 'Done in 1 min 05 s: 2 mailing lists sorted.'
        assert lines[2] == '  2026-09-22.md  103 entries, 101 new or with matching keywords'
        assert lines[3] == '  2026-09-23.md  1 entry, 1 new or with matching keywords'
        assert lines[4] == f'Saved in {Path("abstracts")}'

    def test_finished_without_files(self):
        status, lines = final_message(Outcome.FINISHED, 3, [])

        assert status == 'Done: nothing new to sort'
        assert lines == [SEPARATOR, 'Done in 3 s: nothing new.', SEPARATOR]

    def test_stopped_lists_files_already_written(self):
        status, lines = final_message(Outcome.STOPPED, 30, WRITTEN[:1])

        assert status == 'Stopped'
        assert lines[1] == 'Stopped after 30 s. 1 mailing list already sorted.'
        assert '2026-09-22.md' in lines[2]

    def test_errors_point_to_the_messages(self):
        status, lines = final_message(Outcome.ERRORS, 5, [])

        assert status == 'Finished with errors'
        assert 'see the messages above' in lines[1]

    def test_failed(self):
        status, lines = final_message(Outcome.FAILED, 1, [])

        assert status == 'Failed'
        assert lines[1] == 'Failed after 1 s (see the messages above).'
