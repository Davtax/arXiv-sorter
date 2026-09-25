import pytest

from app.format_entries import fix_entry
from app.sort_entries import (
    AbstractEnclosure,
    AuthorEnclosure,
    TitleEnclosure,
    _find_overlaps,
    _find_re,
    sort_articles,
)

ENCLOSURE = ['<', '>']


@pytest.mark.parametrize(
    ('indices', 'expected'),
    [
        ([(0, 2), (5, 8)], [(0, 2), (5, 8)]),
        ([(0, 10), (2, 4)], [(0, 10)]),
        ([(2, 4), (2, 10)], [(2, 10)]),
        ([(0, 5), (3, 8)], [(0, 8)]),
    ],
    ids=['disjoint', 'second-inside-first', 'first-inside-second', 'partial-overlap'],
)
def test_find_overlaps(indices, expected):
    assert _find_overlaps(indices) == expected


class TestFindRe:
    def test_highlights_matches_and_returns_first_keyword_index(self):
        text, index = _find_re('Spin qubits in a quantum dot', ['quantum dot', 'spin'], ENCLOSURE)

        assert text == '<Spin> qubits in a <quantum dot>'
        assert index == 0

    def test_no_match(self):
        text, index = _find_re('Nothing here', ['quantum dot'], ENCLOSURE)

        assert text == 'Nothing here'
        assert index is None

    def test_ampersand_requires_every_keyword(self):
        keywords = ['quantum dot&reinforcement learning']

        assert _find_re('A quantum dot', keywords, ENCLOSURE)[1] is None
        text, index = _find_re('Reinforcement learning for a quantum dot', keywords, ENCLOSURE)
        assert index == 0
        assert text == '<Reinforcement learning> for a <quantum dot>'

    def test_regular_expressions(self):
        text, _ = _find_re('spin-orbit and spin orbit', ['spin[- ]orbit'], ENCLOSURE)

        assert text == '<spin-orbit> and <spin orbit>'

    def test_nested_keywords_are_highlighted_once(self):
        text, _ = _find_re('a quantum dot array', ['quantum dot array', 'quantum dot'], ENCLOSURE)

        assert text == 'a <quantum dot array>'

    def test_normalize_ignores_accents_and_hyphens(self):
        text, index = _find_re('D. Fernández, J. Smith-Jones', [r'\bfernandez\b', 'smith jones'], ENCLOSURE,
                               normalize=True)

        assert text == 'D. <Fernández>, J. <Smith-Jones>'
        assert index == 0

    def test_word_boundaries_avoid_partial_names(self):
        assert _find_re('M. Manzanares', [r'\bares\b'], ENCLOSURE, normalize=True)[1] is None


def test_sort_articles_orders_by_match_priority(make_entry):
    entries = [
        make_entry(arxiv_id='plain', title='Unrelated'),
        make_entry(arxiv_id='updated', title='Old stuff', published='2020-01-01T00:00:00Z',
                   updated='2026-09-24T17:00:00Z'),
        make_entry(arxiv_id='second', title='Spin qubits'),
        make_entry(arxiv_id='author', title='Other', authors=('D. Fernández',)),
        make_entry(arxiv_id='first', summary='We study a quantum dot.'),
    ]
    for entry in entries:
        fix_entry(entry)

    result = sort_articles(entries, keywords_list=['quantum dot', 'spin'], authors_list=[r'\bfernandez\b'])

    assert [entry.id.split('/')[-1] for entry in result] == ['author', 'first', 'second', 'plain', 'updated']
    assert [entry.index for entry in result] == [4, 4, 3, 0, -1]
    assert all(entry.last_new is False for entry in result)

    author, first, second = result[:3]
    assert author.authors == f'D. {AuthorEnclosure[0]}Fernández{AuthorEnclosure[1]}'
    assert first.summary == f'We study a {AbstractEnclosure[0]}quantum dot{AbstractEnclosure[1]}.'
    assert second.title == f'{TitleEnclosure[0]}Spin{TitleEnclosure[1]} qubits'
