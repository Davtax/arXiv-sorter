"""
User configuration of the GUI.
"""
import json
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path

from arxorter.system import max_threads

SETTINGS_FILE = 'settings.json'
THEMES = ('system', 'light', 'dark')  # 'system' follows the light or dark mode of the operating system


@dataclass
class Settings:
    """
    User configuration of the GUI, saved as a JSON file between sessions.
    The options are phrased positively (e.g. include figures), and translated to the flags of the command line program.
    """
    keywords_dir: str = ''
    abstracts_dir: str = ''

    images: bool = True  # --image removes them
    threads: int = 1  # To detect the figures, limited to the CPUs of the system when loaded
    separate: bool = False
    sort_authors: bool = True  # --modify disables it
    update: bool = False
    verbose: bool = False

    custom_dates: bool = False
    date_0: str = ''  # ISO format, YYYY-MM-DD
    date_f: str = ''

    theme: str = 'system'  # One of THEMES
    skipped_version: str = ''  # Release the user chose to skip, e.g. v0.4.0, so it is not offered again
    window_geometry: str = ''  # Base64 encoded Qt geometry

    @classmethod
    def load(cls, path: Path, default_dir: Path) -> Settings:
        """
        Load the settings from the JSON file, falling back to the defaults for missing or invalid values.
        """
        settings = cls(keywords_dir=str(default_dir), abstracts_dir=str(default_dir / 'abstracts'))

        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return settings
        if not isinstance(data, dict):
            return settings

        for field in fields(cls):
            value = data.get(field.name)
            if isinstance(value, type(getattr(settings, field.name))):
                setattr(settings, field.name, value)

        # The file may come from another computer, with a different number of CPUs
        settings.threads = min(max(settings.threads, 1), max_threads())
        if settings.theme not in THEMES:
            settings.theme = 'system'

        return settings

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=4), encoding='utf-8')

    def to_cli_args(self) -> list[str]:
        """
        Command line arguments of arxorter.cli equivalent to these settings.
        """
        args = ['--directory', self.keywords_dir, '--abstracts', self.abstracts_dir, '--exit']

        if self.verbose:
            args.append('--verbose')
        if self.images:
            args += ['--threads', str(self.threads)]
        else:
            args.append('--image')
        if self.separate:
            args.append('--separate')
        if not self.sort_authors:
            args.append('--modify')
        if self.update:
            args.append('--update')

        if self.custom_dates:
            args += ['--date0', _cli_date(self.date_0), '--datef', _cli_date(self.date_f)]

        return args


def _cli_date(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime('%Y%m%d')
