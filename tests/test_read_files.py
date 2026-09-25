from app.read_files import read_user_file


def test_missing_file_is_created_in_nested_directory(tmp_path):
    file_path = tmp_path / 'keyword files' / 'keywords.txt'

    assert read_user_file(file_path) == []
    assert file_path.is_file()


def test_lines_are_normalized_and_deduplicated(tmp_path):
    file_path = tmp_path / 'keywords.txt'
    file_path.write_text('Quantum Dot\nquantum dot  \n\nFernández\nfernandez\n', encoding='utf-8')

    assert read_user_file(file_path) == ['quantum dot', 'fernandez']


def test_comments_and_blank_lines_are_ignored(tmp_path):
    file_path = tmp_path / 'keywords.txt'
    file_path.write_text('# quant-ph\n   \n  # indented comment\nspin[- ]qubit\n', encoding='utf-8')

    assert read_user_file(file_path) == ['spin[- ]qubit']


def test_file_is_left_untouched_without_sort(tmp_path):
    file_path = tmp_path / 'authors.txt'
    content = 'Zumbuhl\n\nBurkard\n'
    file_path.write_text(content, encoding='utf-8')

    read_user_file(file_path)

    assert file_path.read_text(encoding='utf-8') == content


def test_sort_rewrites_the_file_alphabetically(tmp_path):
    file_path = tmp_path / 'authors.txt'
    file_path.write_text('Zumbuhl\n\nBurkard\nD+Loss\n', encoding='utf-8')

    assert read_user_file(file_path, sort=True) == ['burkard', 'd+loss', 'zumbuhl']
    assert file_path.read_text(encoding='utf-8') == 'Burkard\nD+Loss\nZumbuhl\n'
