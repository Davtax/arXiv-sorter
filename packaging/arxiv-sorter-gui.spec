# PyInstaller build of the GUI, run from the root of the repository with
#     pyinstaller packaging/arxiv-sorter-gui.spec
#
# Windows and Linux: a single executable, arXiv-sorter-GUI(.exe). It unpacks itself in a temporary folder when it starts,
# and the command line program it launches (the GUI binary runs itself with --worker) reuses that folder.
# macOS: an .app bundle, which the Finder already shows as a single file (PyInstaller deprecates single file bundles).
import sys
from pathlib import Path

from packaging.version import Version

from arxiv_sorter import __version__

ROOT = Path(SPECPATH).parent
NAME = 'arXiv-sorter'
EXE_NAME = NAME if sys.platform == 'darwin' else f'{NAME}-GUI'
BUNDLE_ID = 'io.github.davtax.arxiv-sorter'

# Optional icons, exported from logo/arxiv-sorter-icon.af (Linux desktops take the icon from a .desktop file instead)
ICON_FILES = {'win32': ROOT / 'logo' / 'arxiv-sorter.ico', 'darwin': ROOT / 'logo' / 'arxiv-sorter.icns'}
icon_file = ICON_FILES.get(sys.platform)
icon = str(icon_file) if icon_file is not None and icon_file.is_file() else None


def windows_version_info():
    """
    Version resource shown in the properties of the executable in Windows.
    """
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numbers = (Version(__version__).release + (0, 0, 0, 0))[:4]
    strings = [
        StringStruct('ProductName', NAME),
        StringStruct('FileDescription', NAME),
        StringStruct('ProductVersion', __version__),
        StringStruct('FileVersion', __version__),
        StringStruct('OriginalFilename', f'{EXE_NAME}.exe'),
        StringStruct('InternalName', EXE_NAME),
        StringStruct('LegalCopyright', 'MIT License'),
    ]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[StringFileInfo([StringTable('040904B0', strings)]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
    )


a = Analysis(
    [str(ROOT / 'gui.py')],
    pathex=[str(ROOT / 'src')],
    excludes=['tkinter'],
)
pyz = PYZ(a.pure)

options = dict(
    name=EXE_NAME,
    console=False,  # No terminal window (Windows) and a proper application (macOS)
    icon=icon,
    version=windows_version_info() if sys.platform == 'win32' else None,
    upx=False,  # Compressed binaries are slower to start and more often flagged by antivirus programs
)

if sys.platform != 'darwin':
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
    app = BUNDLE(
        coll,
        name=f'{NAME}.app',
        icon=icon,
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            'CFBundleDisplayName': NAME,
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
            'LSApplicationCategoryType': 'public.app-category.productivity',
            'NSHighResolutionCapable': True,  # Sharp text on Retina displays
            'NSRequiresAquaSystemAppearance': False,  # Follow the dark mode of the system
        },
    )
