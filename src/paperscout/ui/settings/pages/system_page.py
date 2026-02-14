from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QFormLayout, QLineEdit, QMessageBox


class SystemPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._final_output_paper_count = 5
        self._arxiv_fetch_max_results = 20

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("系统参数")
        title.setStyleSheet("font-weight:700; font-size:14px;")
        root.addWidget(title)

        tip = QLabel("配置初始化流程中的默认论文数量参数。")
        tip.setStyleSheet("color:#666;")
        root.addWidget(tip)

        card = QFrame()
        card.setStyleSheet("QFrame{border:1px solid #eeeeee;border-radius:12px;background:#ffffff;}")
        root.addWidget(card)

        form_wrap = QVBoxLayout(card)
        form_wrap.setContentsMargins(12, 12, 12, 12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.ed_final_output = QLineEdit()
        self.ed_final_output.setPlaceholderText("默认 5（范围 1~50）")

        self.ed_arxiv_fetch = QLineEdit()
        self.ed_arxiv_fetch.setPlaceholderText("默认 20（范围 5~100）")

        form.addRow("最终输出论文数量", self.ed_final_output)
        form.addRow("arXiv API 输出论文数量", self.ed_arxiv_fetch)
        form_wrap.addLayout(form)
        root.addStretch(1)

    def load(self, settings: Dict[str, Any]) -> None:
        system_cfg = (settings.get("system", {}) or {}) if isinstance(settings, dict) else {}
        if not isinstance(system_cfg, dict):
            system_cfg = {}

        try:
            self._final_output_paper_count = int(system_cfg.get("final_output_paper_count", 5))
        except Exception:
            self._final_output_paper_count = 5
        self._final_output_paper_count = max(1, min(50, self._final_output_paper_count))

        try:
            self._arxiv_fetch_max_results = int(system_cfg.get("arxiv_fetch_max_results", 20))
        except Exception:
            self._arxiv_fetch_max_results = 20
        self._arxiv_fetch_max_results = max(5, min(100, self._arxiv_fetch_max_results))

        self.ed_final_output.setText(str(self._final_output_paper_count))
        self.ed_arxiv_fetch.setText(str(self._arxiv_fetch_max_results))

    def dump(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        system_cfg = settings.setdefault("system", {}) if isinstance(settings, dict) else {}
        if isinstance(system_cfg, dict):
            system_cfg["final_output_paper_count"] = self._final_output_paper_count
            system_cfg["arxiv_fetch_max_results"] = self._arxiv_fetch_max_results
        return settings

    def validate_or_warn(self, parent=None) -> bool:
        final_text = str(self.ed_final_output.text() or "").strip()
        fetch_text = str(self.ed_arxiv_fetch.text() or "").strip()

        try:
            final_count = int(final_text or "5")
        except Exception:
            QMessageBox.warning(parent, "提示", "最终输出论文数量必须是整数。")
            return False

        try:
            fetch_count = int(fetch_text or "20")
        except Exception:
            QMessageBox.warning(parent, "提示", "arXiv API 输出论文数量必须是整数。")
            return False

        if final_count < 1 or final_count > 50:
            QMessageBox.warning(parent, "提示", "最终输出论文数量范围应为 1~50。")
            return False

        if fetch_count < 5 or fetch_count > 100:
            QMessageBox.warning(parent, "提示", "arXiv API 输出论文数量范围应为 5~100。")
            return False

        if fetch_count < final_count:
            QMessageBox.warning(parent, "提示", "arXiv API 输出论文数量不能小于最终输出论文数量。")
            return False

        self._final_output_paper_count = final_count
        self._arxiv_fetch_max_results = fetch_count
        return True
