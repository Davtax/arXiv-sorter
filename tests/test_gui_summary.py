from pathlib import Path

import pytest

from arxorter.gui.search_files import SEARCH_FILES, count_terms, describe
from arxorter.gui.summary import Outcome, WrittenFile, final_message, format_duration

WRITTEN = [
    WrittenFile(Path('abstracts') / '2026-09-22.md', 103, 101),
    WrittenFile(Path('abstracts') / '2026-09-23.md', 1, 1),
]
KEYWORDS, AUTHORS, CATEGORIES = SEARCH_FILES


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
        summary = final_message(Outcome.FINISHED, 65, WRITTEN)

        assert summary.status == 'Done: 2 mailing lists sorted'
        assert summary.folder == Path('abstracts')
        assert summary.lines() == [
            '🎉 Done in 1 min 05 s: 2 mailing lists sorted.',
            '  2026-09-22.md  103 entries, 101 new or matching your keywords',
            '  2026-09-23.md  1 entry, 1 new or matching your keywords',
            f'Saved in {Path("abstracts")}',
        ]

    def test_warnings_are_counted(self):
        summary = final_message(Outcome.FINISHED, 5, WRITTEN, n_warnings=2)

        assert summary.headline == 'Done in 5 s: 2 mailing lists sorted (2 warnings, see the messages above).'

    def test_finished_without_files(self):
        summary = final_message(Outcome.FINISHED, 3, [])

        assert summary.status == 'Done: nothing new to sort'
        assert summary.lines() == ['✅ Done in 3 s: nothing new to sort.']

    def test_stopped_lists_files_already_written(self):
        summary = final_message(Outcome.STOPPED, 30, WRITTEN[:1])

        assert summary.status == 'Stopped'
        assert summary.headline == 'Stopped after 30 s. 1 mailing list already sorted.'
        assert '2026-09-22.md' in summary.lines()[1]

    def test_errors_point_to_the_messages(self):
        summary = final_message(Outcome.ERRORS, 5, [])

        assert summary.status == 'Finished with errors'
        assert 'see the messages above' in summary.headline

    def test_failed(self):
        summary = final_message(Outcome.FAILED, 1, [])

        assert (summary.status, summary.headline) == ('Failed', 'Failed after 1 s (see the messages above).')

    def test_files_in_several_folders(self):
        files = [WRITTEN[0], WrittenFile(Path('other') / '2026-09-24.md', 5, 5)]

        summary = final_message(Outcome.FINISHED, 1, files)

        assert summary.folder is None
        assert summary.lines()[-1] == 'Saved in several folders'


class TestSearchFiles:
    def test_counts_terms_without_comments_nor_blank_lines(self, tmp_path):
        path = tmp_path / 'keywords.txt'
        path.write_text('quantum dot\n\n# spin qubit\n  \nspin[- ]orbit&qubit\n', encoding='utf-8')

        assert count_terms(path) == 2

    def test_missing_file(self, tmp_path):
        assert count_terms(tmp_path / 'keywords.txt') is None

    @pytest.mark.parametrize(('search_file', 'count', 'expected'), [
        (KEYWORDS, 4, '🔑 4 keywords'),
        (AUTHORS, 1, '👤 1 author'),
        (AUTHORS, 0, '👤 no authors'),
        (CATEGORIES, None, '🏷 all categories'),  # An empty categories file requests all of them
        (CATEGORIES, 2, '🏷 2 categories'),
    ])
    def test_description(self, search_file, count, expected):
        assert describe(search_file, count) == expected
