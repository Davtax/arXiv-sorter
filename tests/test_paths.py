import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.dates_functions import check_last_date
from app.pdf_scrapper import detect_figure, get_images_pdf_scrapper
from app.read_files import read_user_file


class PathManagementTests(unittest.TestCase):
    def test_user_file_is_created_in_nested_space_containing_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / 'keyword files' / 'keywords.txt'

            self.assertEqual(read_user_file(file_path), [])
            self.assertTrue(file_path.is_file())

    def test_last_date_uses_matching_files_or_directories_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            abstracts_dir = Path(temporary_directory)
            (abstracts_dir / '2026-01-02.md').touch()
            (abstracts_dir / 'figures').mkdir()
            (abstracts_dir / '2026-01-03').mkdir()

            self.assertEqual(check_last_date(abstracts_dir, False), datetime(2026, 1, 2))
            self.assertEqual(check_last_date(abstracts_dir, True), datetime(2026, 1, 3))

    @patch('app.pdf_scrapper.run')
    def test_java_arguments_keep_space_containing_paths_intact(self, run_mock):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path_with_space = Path(temporary_directory) / 'pdf files'
            data_path = Path(temporary_directory) / 'json files'
            detect_figure(path_with_space, data_path, 2)

            self.assertEqual(
                run_mock.call_args.args[0],
                ['java', '-jar', Path('.arXiv_sorter') / 'pdffigures2-0.0.12.jar', path_with_space,
                 '-e', '-t', '2', '-d', data_path, '-q'],
            )

    @patch('app.pdf_scrapper.extract_from_json', return_value=True)
    @patch('app.pdf_scrapper.detect_figure')
    @patch('app.pdf_scrapper.download_pdfs')
    @patch('app.pdf_scrapper.check_pdffigure2')
    @patch('app.pdf_scrapper.check_java', return_value=True)
    def test_figures_follow_custom_abstracts_directory(self, *_mocks):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            abstracts_dir = root / 'custom output'
            temp_dir = SimpleNamespace(name=str(root / 'temporary files'))

            links = get_images_pdf_scrapper(
                '2026-01-02', [SimpleNamespace(id='https://arxiv.org/abs/1234.5678')], temp_dir,
                abstracts_dir, False,
            )

            self.assertTrue((abstracts_dir / 'figures' / '2026-01-02').is_dir())
            self.assertEqual(links, ['figures/2026-01-02/1234.5678.png'])


if __name__ == '__main__':
    unittest.main()
