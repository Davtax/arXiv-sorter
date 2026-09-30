# PyInstaller build of the GUI, run from the root of the repository with
#     pyinstaller packaging/arxorter-gui.spec
#
# Windows and Linux: a single executable, arXorter-GUI-Windows.exe or arXorter-GUI-Ubuntu. It unpacks itself in
# a temporary folder when it starts, and the command line program it launches (the GUI binary runs itself with --worker)
# reuses that folder.
# macOS: an .app bundle, arXorter-GUI-macOS.app, which the Finder already shows as a single file (PyInstaller
# deprecates single file bundles). The executable inside is just arXorter, the name of its processes (e.g. in the
# Activity Monitor).
# The file names end with the system, like the command line binaries (arXorter-CLI-<system>) and the release assets.
import sys
from pathlib import Path

from packaging.version import Version

from arxorter import __version__
from arxorter.gui.icons import APP_ICON_ICNS, APP_ICON_ICO, APP_ICON_PNG
from arxorter.updater import asset_name, get_system_name

ROOT = Path(SPECPATH).parent
NAME = 'arXorter'
EXE_NAME = asset_name(get_system_name(), gui=True)  # e.g. arXorter-GUI-Windows
BUNDLE_ID = 'io.github.davtax.arxorter'

# Icon of the program file, and the image of the application icon used by the GUI (see arxorter/gui/icons.py). Linux
# desktops take the icon from a .desktop file instead
icon = {'win32': str(APP_ICON_ICO), 'darwin': str(APP_ICON_ICNS)}.get(sys.platform)


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
    datas=[(str(APP_ICON_PNG), 'arxorter/gui/app-icon')],
    excludes=['tkinter'],
)
pyz = PYZ(a.pure)

options = dict(
    name=NAME if sys.platform == 'darwin' else EXE_NAME,  # Only the bundle has the system in its name on macOS
    console=False,  # No terminal window (Windows) and a proper application (macOS)
    icon=icon,
    version=windows_version_info() if sys.platform == 'win32' else None,
    upx=False,  # Compressed binaries are slower to start and more often flagged by antivirus programs
)

if sys.platform != 'darwin':
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, name=EXE_NAME, upx=False)
    app = BUNDLE(
        coll,
        name=f'{EXE_NAME}.app',
        icon=icon,
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            'CFBundleName': NAME,  # In the menu bar, instead of the name of the bundle
            'CFBundleDisplayName': NAME,
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
            'LSApplicationCategoryType': 'public.app-category.productivity',
            'NSHighResolutionCapable': True,  # Sharp text on Retina displays
            'NSRequiresAquaSystemAppearance': False,  # Follow the dark mode of the system
        },
    )
