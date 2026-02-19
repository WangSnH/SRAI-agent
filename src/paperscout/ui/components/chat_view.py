from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTextBrowser


class ChatView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatView")
        self.setOpenExternalLinks(True)
        # Ensure viewport paints its own background (prevents black/white blocks)
        self.viewport().setAutoFillBackground(True)

    def set_html_and_scroll_bottom(self, html: str):
        self.setHtml(html)
        # Scroll after the document/layout is updated
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))
