from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QLabel, QToolButton,
    QListWidget, QListWidgetItem, QStackedWidget, QMessageBox
)

from paperscout.config.settings import load_settings, save_settings
from .pages.llm_page import LLMPage
from .pages.system_page import SystemPage


class SettingsWindow(QDialog):
    """
    设置窗口（左右布局）：
    - 顶部：标题 + 关闭(✕)（不保存）
    - 左侧：导航
    - 右侧：页面（目前只有“AI 模型配置”页）
    - 底部：仅“确认保存”
    - 只有点击“确认保存”才会写入配置；关闭(✕)直接退出不保存
    """
    settings_saved = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("设置")
        self.resize(900, 560)
        self.setModal(True)

        # 强制设置页使用浅色主题，避免 macOS 深色模式下内容区域发黑/低对比
        self.setStyleSheet(
            """
            QDialog#SettingsDialog {
                background: #ffffff;
                color: #111111;
            }
            QDialog#SettingsDialog QFrame#SettingsBody {
                background: #f7f8fa;
            }
            QDialog#SettingsDialog QStackedWidget {
                background: #f7f8fa;
            }
            QDialog#SettingsDialog QLabel {
                color: #111111;
            }
            QDialog#SettingsDialog QLineEdit,
            QDialog#SettingsDialog QComboBox,
            QDialog#SettingsDialog QListWidget,
            QDialog#SettingsDialog QTabWidget::pane,
            QDialog#SettingsDialog QWidget {
                selection-background-color: #eaf3ff;
            }
            """
        )

        self._original: Dict[str, Any] = load_settings()
        self._working: Dict[str, Any] = deepcopy(self._original)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- Header ----------
        header = QFrame()
        header.setStyleSheet("QFrame{background:#ffffff;border-bottom:1px solid #eeeeee;}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 10, 12, 10)

        title = QLabel("设置")
        title.setStyleSheet("font-weight:700; font-size:14px;")

        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setToolTip("关闭（不保存）")

        hl.addWidget(title, 1)
        hl.addWidget(btn_close, 0)
        root.addWidget(header)

        # ---------- Body ----------
        body = QFrame()
        body.setObjectName("SettingsBody")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        self.nav.setStyleSheet("""
            QListWidget{background:#ffffff;border-right:1px solid #e8e8e8;}
            QListWidget::item{padding:10px 12px;}
            QListWidget::item:selected{background:#eaf3ff;}
        """)

        self.pages = QStackedWidget()
        self.page_llm = LLMPage()
        self.page_system = SystemPage()
        self.pages.addWidget(self.page_llm)
        self.pages.addWidget(self.page_system)

        self._add_nav("配置 AI 模型", 0)
        self._add_nav("系统参数", 1)
        self._add_nav("（预留）导出", -1)
        self.nav.setCurrentRow(0)

        bl.addWidget(self.nav)
        bl.addWidget(self.pages, 1)
        root.addWidget(body, 1)

        # ---------- Footer ----------
        footer = QFrame()
        footer.setStyleSheet("QFrame{background:#ffffff;border-top:1px solid #eeeeee;}")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 10, 12, 10)

        fl.addStretch(1)

        self.btn_ok = QPushButton("确认保存")
        self.btn_ok.setStyleSheet(
            "QPushButton{background:#1677ff;color:white;border:none;padding:8px 14px;border-radius:10px;}"
        )
        self.btn_ok.setCursor(Qt.PointingHandCursor)

        fl.addWidget(self.btn_ok)
        root.addWidget(footer)

        # Load settings into page
        self.page_llm.load(self._working)
        self.page_system.load(self._working)

        # Signals
        btn_close.clicked.connect(self.reject)  # 关闭：不保存
        self.btn_ok.clicked.connect(self._save)
        self.nav.currentRowChanged.connect(self._nav_changed)

    def _add_nav(self, text: str, page_index: int):
        it = QListWidgetItem(text)
        it.setData(Qt.UserRole, page_index)
        self.nav.addItem(it)

    def _nav_changed(self, row: int):
        it = self.nav.item(row)
        if not it:
            return
        idx = it.data(Qt.UserRole)
        if idx is None or idx < 0:
            QMessageBox.information(self, "提示", "该页面尚未实现。")
            self.nav.setCurrentRow(0)
            return
        self.pages.setCurrentIndex(idx)

    def _save(self):
        # 只有点“确认保存”才保存
        if not self.page_llm.validate_or_warn(self):
            return
        if not self.page_system.validate_or_warn(self):
            return

        # 写入页面状态到 working settings
        self.page_llm.dump(self._working)
        self.page_system.dump(self._working)

        # 落盘
        save_settings(self._working)

        # 通知主窗口刷新
        self.settings_saved.emit(self._working)
        self.accept()
