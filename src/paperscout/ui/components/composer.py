from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QToolButton, QTextEdit, QPushButton, QSizePolicy, QSpacerItem


class Composer(QWidget):
    send_clicked = Signal(str)
    model_clicked = Signal()   # 点击 🤖
    # 你后面可以继续加 import_clicked / run_clicked / export_clicked 等

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Composer")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(6)

        def icon_btn(text: str, tip: str) -> QToolButton:
            b = QToolButton()
            b.setObjectName("IconBtn")
            b.setText(text)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setAutoRaise(True)
            return b

        self.btn_model = icon_btn("🤖", "模型：选择 AI 模型")
        self.btn_import = icon_btn("📥", "导入（占位）")
        self.btn_rubric = icon_btn("📏", "标准（占位）")
        self.btn_run = icon_btn("▶️", "运行（占位）")
        self.btn_export = icon_btn("📤", "导出（占位）")
        self.btn_more = icon_btn("⋯", "更多")

        for b in [self.btn_model, self.btn_import, self.btn_rubric, self.btn_run, self.btn_export, self.btn_more]:
            tb.addWidget(b)
        tb.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        root.addWidget(toolbar)

        # Input + Send
        row = QHBoxLayout()
        row.setSpacing(10)

        self.input = QTextEdit()
        self.input.setObjectName("InputBox")
        self.input.setPlaceholderText("输入指令…")
        self.input.setFixedHeight(120)

        self.btn_send = QPushButton("发送")
        self.btn_send.setObjectName("SendButton")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setFixedHeight(44)
        self.btn_send.setFixedWidth(96)

        row.addWidget(self.input, 1)
        row.addWidget(self.btn_send, 0, Qt.AlignBottom)

        root.addLayout(row)

        # Signals
        self.btn_model.clicked.connect(self.model_clicked.emit)
        self.btn_send.clicked.connect(self._on_send)

    def _on_send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.send_clicked.emit(text)
