from datetime import datetime

import pytest

from arxiv_sorter import preview
from arxiv_sorter.formatting import fix_entry
from arxiv_sorter.preview import custom_entry, fetch_latest, matching_entries, usable_terms
from arxiv_sorter.search_terms import Kind


@pytest.fixture
def entries(make_entry):
    entries = [
        make_entry(arxiv_id='1v1', title='A spin qubit in germanium', authors=('Alice Smith',)),
        make_entry(arxiv_id='2v1', title='Unrelated', summary='Nothing to see.', authors=('Bob Jones',)),
        make_entry(arxiv_id='3v1', title='Transport', summary='We study spin-orbit coupling.',
                   authors=('Daniel Loss',)),
    ]
    for entry in entries:
        fix_entry(entry)
    return entries


class TestUsableTerms:
    def test_normalized_as_in_the_run(self):
        assert usable_terms(['Quantum Dot', '', '# comment', 'quantum dot', 'Fernández'], Kind.KEYWORDS) == [
            'quantum dot', 'fernandez']

    def test_authors_are_full_words(self):
        assert usable_terms(['Loss'], Kind.AUTHORS) == [r'\bloss\b']

    def test_lines_with_mistakes_are_left_out(self):
        assert usable_terms(['spin[ qubit', 'qubit&', 'transport'], Kind.KEYWORDS) == ['transport']


class TestMatchingEntries:
    def test_keywords_and_authors(self, entries):
        matches = matching_entries(entries, ['spin qubit', 'spin[- ]orbit'], ['Loss'])

        assert [entry.id.rsplit('/', 1)[-1] for entry in matches] == ['1v1', '3v1']
        assert '<span' in matches[0].title  # Highlighted

    def test_the_entries_are_not_modified(self, entries):
        matching_entries(entries, ['spin qubit'], [])

        assert '<span' not in entries[0].title
        assert 'index' not in entries[0]

    def test_no_terms_no_matches(self, entries):
        assert matching_entries(entries, ['# only a comment'], []) == []


class TestCustomEntry:
    def test_matches_like_a_submission(self):
        entry = custom_entry('Hole spin qubits\nin germanium', 'We study  spin-orbit coupling.',
                             ' Daniel Loss ,Guido Burkard, ')

        assert entry.title == 'Hole spin qubits in germanium'
        assert entry.authors == 'Daniel Loss, Guido Burkard'

        matches = matching_entries([entry], ['spin[- ]orbit'], ['Burkard'])
        assert len(matches) == 1
        assert '<span' in matches[0].summary and '<span' in matches[0].authors

    def test_not_found(self):
        assert matching_entries([custom_entry('Unrelated', '', 'Alice Smith')], ['qubit'], ['Loss']) == []


class TestFetchLatest:
    def test_latest_mailing_list_with_submissions(self, monkeypatch, make_entry):
        monday, tuesday = datetime(2026, 9, 21, 18), datetime(2026, 9, 22, 18)
        monkeypatch.setattr(preview, 'search_entries', lambda categories, date_0, date_f: (
            [[make_entry(arxiv_id='old')], []], [monday, tuesday]))

        latest = fetch_latest(['quant-ph'], now=datetime(2026, 9, 23, 10))

        assert latest.date == monday  # Tuesday has no submissions yet
        assert [entry.id.rsplit('/', 1)[-1] for entry in latest.entries] == ['old']
        assert isinstance(latest.entries[0].authors, str)  # Fixed, as in the run

    def test_goes_back_a_few_mailing_lists_at_most(self, monkeypatch):
        calls = []
        monkeypatch.setattr(preview, 'search_entries', lambda categories, date_0, date_f: (
            calls.append(date_0) or ([[]], [date_0])))

        assert fetch_latest([], now=datetime(2026, 9, 23, 10)) is None
        assert len(calls) == preview.MAX_DAYS_BACK
