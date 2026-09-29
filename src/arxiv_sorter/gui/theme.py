"""
Light and dark themes of the window.

The native style of the platform is asked for the color scheme (Qt 6.8+), so the window keeps its native look. Some
styles ignore it (e.g. on some Linux desktops); then the Fusion style is used, with an explicit light or dark palette.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

COLOR_SCHEMES = {'system': Qt.ColorScheme.Unknown, 'light': Qt.ColorScheme.Light, 'dark': Qt.ColorScheme.Dark}

_native_style: str | None = None  # Style of the platform, restored when going back to it from Fusion


def is_dark(palette: QPalette) -> bool:
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def dark_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: '#202124', QPalette.ColorRole.WindowText: '#e8eaed',
        QPalette.ColorRole.Base: '#17181a', QPalette.ColorRole.AlternateBase: '#2a2b2e',
        QPalette.ColorRole.Text: '#e8eaed', QPalette.ColorRole.Button: '#2d2e31',
        QPalette.ColorRole.ButtonText: '#e8eaed', QPalette.ColorRole.ToolTipBase: '#2d2e31',
        QPalette.ColorRole.ToolTipText: '#e8eaed', QPalette.ColorRole.PlaceholderText: '#9aa0a6',
        QPalette.ColorRole.Highlight: '#4c8bf5', QPalette.ColorRole.HighlightedText: '#ffffff',
        QPalette.ColorRole.Link: '#8ab4f8', QPalette.ColorRole.BrightText: '#ff8a80',
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#6f7378'))
    return palette


def apply_theme(app: QApplication, theme: str):
    """
    Apply one of the themes of arxiv_sorter.gui.settings.THEMES.
    """
    global _native_style
    if _native_style is None:
        _native_style = app.style().name()
        # With the system theme, the scheme also changes when the user switches the mode of the operating system
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: refresh_native_style(app))

    if app.style().name() != _native_style:  # Back to the native style, in case Fusion was used before
        app.setStyle(QStyleFactory.create(_native_style))
        app.setPalette(QPalette())  # Palette of the style again, which follows the color scheme
    app.styleHints().setColorScheme(COLOR_SCHEMES.get(theme, Qt.ColorScheme.Unknown))
    app.processEvents()

    if theme != 'system' and is_dark(app.palette()) != (theme == 'dark'):  # The native style ignored the scheme
        app.setStyle(QStyleFactory.create('Fusion'))
        app.setPalette(dark_palette() if theme == 'dark' else app.style().standardPalette())
    else:
        refresh_native_style(app)


def refresh_native_style(app: QApplication):
    """
    Create the native style again, so it computes the colors of every widget for the current scheme.

    The Windows 11 style gives some widgets (e.g. check boxes and radio buttons) their own palette, which it does not
    update correctly when the scheme changes from light to dark: the inactive colors keep the background color, so the
    ticks lose their highlight when another application has the focus (Qt 6.11).
    """
    if app.style().name() == _native_style:  # Not with the Fusion fallback, whose palette is set explicitly
        app.setStyle(QStyleFactory.create(_native_style))
