import pytest

from arxiv_sorter.cli import parse_args
from arxiv_sorter.gui import settings as settings_module
from arxiv_sorter.gui.settings import Settings


class TestSettingsFile:
    def test_defaults_without_file(self, tmp_path):
        settings = Settings.load(tmp_path / 'missing.json', tmp_path)

        assert settings.keywords_dir == str(tmp_path)
        assert settings.abstracts_dir == str(tmp_path / 'abstracts')
        assert settings.images and not settings.verbose

    def test_round_trip(self, tmp_path):
        path = tmp_path / 'config' / 'settings.json'
        settings = Settings(keywords_dir='keys', abstracts_dir='abs', verbose=True, separate=True,
                            custom_dates=True, date_0='2026-09-01', date_f='2026-09-10')

        settings.save(path)

        assert Settings.load(path, tmp_path) == settings

    def test_corrupted_file_uses_defaults(self, tmp_path):
        path = tmp_path / 'settings.json'
        path.write_text('{not json', encoding='utf-8')

        assert Settings.load(path, tmp_path) == Settings.load(tmp_path / 'missing.json', tmp_path)

    def test_invalid_values_are_ignored(self, tmp_path):
        path = tmp_path / 'settings.json'
        path.write_text('{"verbose": "yes", "keywords_dir": 3, "separate": true}', encoding='utf-8')

        settings = Settings.load(path, tmp_path)

        assert settings.verbose is False
        assert settings.keywords_dir == str(tmp_path)
        assert settings.separate is True


class TestCliArgs:
    def test_default_settings_match_cli_defaults(self):
        args = parse_args(Settings(keywords_dir='keys', abstracts_dir='abs').to_cli_args())

        assert args.directory == 'keys' and args.abstracts == 'abs'
        assert args.exit
        assert args.image and args.final and args.modify
        assert not (args.verbose or args.separate or args.update)
        assert args.date0 is None and args.datef is None

    def test_every_option_is_translated(self):
        settings = Settings(keywords_dir='k', abstracts_dir='a', images=False, final_date=False, separate=True,
                            sort_authors=False, update=True, verbose=True,
                            custom_dates=True, date_0='2026-09-01', date_f='2026-09-10')

        args = parse_args(settings.to_cli_args())

        assert not (args.image or args.final or args.modify)
        assert args.separate and args.update and args.verbose
        assert (args.date0, args.datef) == ('20260901', '20260910')

    def test_dates_ignored_without_custom_range(self):
        args = parse_args(Settings(date_0='2026-09-01', date_f='2026-09-10').to_cli_args())

        assert args.date0 is None and args.datef is None

    def test_threads_only_with_figures(self):
        with_figures = parse_args(Settings(images=True, threads=3).to_cli_args())
        without_figures = Settings(images=False, threads=3).to_cli_args()

        assert with_figures.threads == 3
        assert '--threads' not in without_figures


class TestThreadsSetting:
    @pytest.mark.parametrize(('saved', 'expected'), [(1, 1), (3, 3), (16, 4), (0, 1), (-2, 1)])
    def test_limited_to_the_cpus_of_this_system(self, tmp_path, monkeypatch, saved, expected):
        monkeypatch.setattr(settings_module, 'max_threads', lambda: 4)
        path = tmp_path / 'settings.json'
        path.write_text(f'{{"threads": {saved}}}', encoding='utf-8')

        assert Settings.load(path, tmp_path).threads == expected
