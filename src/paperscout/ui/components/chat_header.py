from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton


class ChatHeader(QWidget):
    settings_clicked = Signal()

    def __init__(self, title: str = "PaperScout", parent=None):
        super().__init__(parent)
        self.setObjectName("ChatHeader")

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("ChatTitle")

        self.lbl_subtitle = QLabel("当前模型：-")
        self.lbl_subtitle.setObjectName("ChatSubtitle")

        box.addWidget(self.lbl_title)
        box.addWidget(self.lbl_subtitle)

        root.addLayout(box, 1)

        self.btn_settings = QToolButton()
        self.btn_settings.setText("⚙️")
        self.btn_settings.setObjectName("IconBtn")
        self.btn_settings.setToolTip("设置")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        root.addWidget(self.btn_settings)

        self.btn_settings.clicked.connect(self.settings_clicked.emit)

    def set_subtitle(self, text: str):
        self.lbl_subtitle.setText(text)
