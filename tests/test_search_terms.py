import pytest

from arxorter.search_terms import Kind, Problem, Severity, check_folder, check_lines


class TestKeywords:
    def test_valid_lines(self):
        lines = ['quantum dot', 'spin[- ]orbit&spin qubit', '# spin[ commented', '', '   ', r'\bqubits?\b']

        assert check_lines(lines, Kind.KEYWORDS) == []

    def test_invalid_regular_expression_names_its_line(self):
        problems = check_lines(['quantum dot', '', 'spin[ qubit'], Kind.KEYWORDS)

        assert problems == [Problem('keywords.txt', 3, 'spin[ qubit',
                                    'invalid regular expression, unterminated character set at position 4')]
        assert str(problems[0]) == ("keywords.txt, line 3: invalid regular expression, unterminated character set at "
                                    "position 4 ('spin[ qubit')")

    def test_only_the_wrong_term_of_a_combination(self):
        problems = check_lines(['quantum dot&spin (qubit'], Kind.KEYWORDS)

        assert [problem.text for problem in problems] == ['spin (qubit']

    @pytest.mark.parametrize('line', ['quantum dot&', '&spin', 'a&&b', 'a& &b'])
    def test_empty_terms_would_match_everything(self, line):
        problems = check_lines([line], Kind.KEYWORDS)

        assert [problem.severity for problem in problems] == [Severity.ERROR]
        assert 'empty term' in problems[0].message


class TestAuthors:
    def test_names_with_accents_and_patterns(self):
        assert check_lines(['D. Fernández', r'M[^,]* +Ares', 'Löwdin'], Kind.AUTHORS) == []

    def test_invalid_pattern(self):
        assert [problem.line for problem in check_lines(['Loss', 'M[^,* Ares'], Kind.AUTHORS)] == [2]


class TestCategories:
    @pytest.mark.parametrize('category', ['quant-ph', 'cond-mat', 'cond-mat.mes-hall', 'cs.LG', 'physics.atom-ph',
                                          'q-bio.NC', 'math'])
    def test_arxiv_categories(self, category):
        assert check_lines([category], Kind.CATEGORIES) == []

    @pytest.mark.parametrize('category', ['quant ph', 'cond-mat mes-hall', 'cs.*', 'quant-ph,cond-mat'])
    def test_suspicious_categories_are_warnings(self, category):
        problems = check_lines([category], Kind.CATEGORIES)

        assert [problem.severity for problem in problems] == [Severity.WARNING]


def test_folder_checks_the_three_files(tmp_path):
    (tmp_path / 'keywords.txt').write_text('ok\nbad[\n', encoding='utf-8')
    (tmp_path / 'authors.txt').write_text('Loss\n', encoding='utf-8')
    # categories.txt is missing: the program creates it empty

    problems = check_folder(tmp_path)

    assert [(problem.filename, problem.line) for problem in problems] == [('keywords.txt', 2)]
