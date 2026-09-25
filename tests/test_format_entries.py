import io
from datetime import datetime

import pytest

from app.format_entries import (
    _fix_equation_inner,
    _remove_white_spaces,
    fix_entry,
    write_article,
    write_document,
)


def _prepared(entry, index: int, last_new: bool = False):
    """Entry in the state that `write_document` expects: fixed and sorted."""
    fix_entry(entry)
    entry['index'] = index
    entry['last_new'] = last_new
    return entry


def test_remove_white_spaces_collapses_runs():
    assert _remove_white_spaces('a  b     c d') == 'a b c d'


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('energy $ E_0 $ is', 'energy $E_0$ is'),
        ('scales as $N$2 times', 'scales as $N$ 2 times'),
        ('$a$ and $ b $', '$a$ and $b$'),
        ('x &lt; y &gt; z', 'x < y > z'),
        ('costs 5$', 'costs 5$'),
        ('unclosed $x', 'unclosed $x'),
    ],
    ids=['inner-spaces', 'number-after', 'multiple', 'html-entities', 'trailing-dollar', 'unclosed'],
)
def test_fix_equation_inner(text, expected):
    assert _fix_equation_inner(text) == expected


class TestFixEntry:
    def test_new_entry(self, make_entry):
        entry = make_entry(
            title='A  long\n title with `quotes`',
            summary='Line one\n line  two',
            authors=('Alice Smith', 'Bob Jones'),
            published='2026-09-24T17:59:03Z',
        )

        fix_entry(entry)

        assert entry.title == "A long title with 'quotes'"
        assert entry.summary == 'Line one line two'
        assert entry.authors == 'Alice Smith, Bob Jones'
        assert entry.updated == 'Thu, 24 Sep 2026 17:59:03 GMT'
        assert entry.updated_bool is False

    def test_updated_entry_is_flagged(self, make_entry):
        entry = make_entry(published='2026-01-01T10:00:00Z', updated='2026-09-24T17:59:03Z')

        fix_entry(entry)

        assert entry.title == 'A title *(UPDATED)*'
        assert entry.updated_bool is True

    def test_fields_are_stored_as_dict_items(self, make_entry):
        entry = make_entry(authors=('Alice Smith', 'Bob Jones'))

        fix_entry(entry)

        assert entry['authors'] == entry.authors == 'Alice Smith, Bob Jones'


class TestWriteArticle:
    def test_single_author_with_image(self, make_entry):
        entry = _prepared(make_entry(), index=1)
        f = io.StringIO()

        write_article(entry, f, 0, 3, image_url='figures/x.png')

        text = f.getvalue()
        assert text.startswith('(1 / 3)\n\nTitle: **A title**\n\nAuthor: Alice Smith\n\n')
        assert "<img src='figures/x.png'" in text
        assert 'http://arxiv.org/abs/2609.01234v1' in text
        assert text.endswith('---\n')

    def test_multiple_authors_without_image(self, make_entry):
        entry = _prepared(make_entry(authors=('A', 'B')), index=1)
        f = io.StringIO()

        write_article(entry, f, 0, 1)

        assert 'Authors: A, B' in f.getvalue()
        assert '<img' not in f.getvalue()

    def test_last_new_entry_gets_double_separator(self, make_entry):
        entry = _prepared(make_entry(), index=1, last_new=True)
        f = io.StringIO()

        write_article(entry, f, 0, 1)

        assert f.getvalue().endswith('---\n\n---\n')


class TestWriteDocument:
    @pytest.fixture
    def entries(self, make_entry):
        return [
            _prepared(make_entry(arxiv_id='2609.00001v1'), index=2),
            _prepared(make_entry(arxiv_id='2609.00002v1'), index=1, last_new=True),
            _prepared(make_entry(arxiv_id='2609.00003v2'), index=-1),
        ]

    def test_joined_file(self, tmp_path, entries):
        write_document(entries, datetime(2026, 9, 24), tmp_path, final=True, separate_files=False,
                       image_urls=['img.png', None], version='1.2.3')

        text = (tmp_path / '2026-09-24.md').read_text(encoding='utf-8')
        assert [line for line in text.splitlines() if line.startswith('(')] == ['(1 / 2)', '(2 / 2)', '(1 / 1)']
        assert text.count('<img') == 1
        assert text.rstrip().endswith('with arXiv-sorter version: 1.2.3*')

    def test_joined_file_without_footer(self, tmp_path, entries):
        write_document(entries, datetime(2026, 9, 24), tmp_path, final=False, separate_files=False,
                       image_urls=[None, None])

        assert 'This file was created at' not in (tmp_path / '2026-09-24.md').read_text(encoding='utf-8')

    def test_separate_files(self, tmp_path, entries):
        write_document(entries, datetime(2026, 9, 24), tmp_path, final=True, separate_files=True,
                       image_urls=[None, None])

        folder = tmp_path / '2026-09-24'
        names = sorted(path.name for path in folder.iterdir())
        assert names == ['0_2609.00001v1.md', '1_2609.00002v1.md', '2_2609.00003v2.md']

        headers = [(folder / name).read_text(encoding='utf-8').splitlines()[0] for name in names]
        assert headers == ['(1 / 2)', '(2 / 2)', '(1 / 1)']
