import os
import sys

# macOS: prevent dark-mode black blocks & ensure crisp HiDPI rendering
if sys.platform == "darwin":
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication, QStyleFactory
from .ui.main_window import MainWindow


def _apply_light_palette(app: QApplication) -> None:
    """Force a light palette so dark-mode / high-contrast themes don't break the UI."""
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#f5f6f7"))
    pal.setColor(QPalette.WindowText, QColor("#111111"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#f2f4f7"))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipText, QColor("#111111"))
    pal.setColor(QPalette.Text, QColor("#111111"))
    pal.setColor(QPalette.PlaceholderText, QColor("#999999"))
    pal.setColor(QPalette.Button, QColor("#f2f4f7"))
    pal.setColor(QPalette.ButtonText, QColor("#111111"))
    pal.setColor(QPalette.BrightText, QColor("#ff0000"))
    pal.setColor(QPalette.Link, QColor("#1677ff"))
    pal.setColor(QPalette.Highlight, QColor("#1677ff"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PaperScout")

    # Use Fusion style on all platforms for consistent rendering
    # Avoids macOS Aqua artefacts and Windows native style QSS conflicts
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")

    _apply_light_palette(app)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())
