from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QFormLayout, QLineEdit, QMessageBox, QComboBox

from paperscout.config.settings import SENTENCE_TRANSFORMER_MODEL_OPTIONS


class SystemPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._final_output_paper_count = 5
        self._arxiv_api_default_max_results = 30
        self._arxiv_fetch_max_results = 40
        self._second_prompt_truncate_count = 40
        self._weight_relevance = 0.50
        self._weight_novelty = 0.25
        self._weight_recency = 0.20
        self._weight_citation = 0.05
        self._sentence_transformer_model = "BAAI/bge-large-en-v1.5"
        self._zh2en_translation_cache_size = 3

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("系统参数")
        title.setStyleSheet("font-weight:700; font-size:14px;")
        root.addWidget(title)

        tip = QLabel("配置初始化流程参数与评分权重（权重会自动归一化）。")
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

        self.ed_arxiv_api_default = QLineEdit()
        self.ed_arxiv_api_default.setPlaceholderText("默认 30（范围 5~300）")

        self.ed_arxiv_fetch = QLineEdit()
        self.ed_arxiv_fetch.setPlaceholderText("默认 40（范围 5~300）")

        self.ed_second_prompt_truncate = QLineEdit()
        self.ed_second_prompt_truncate.setPlaceholderText("默认 40（范围 5~200）")

        self.ed_weight_relevance = QLineEdit()
        self.ed_weight_relevance.setPlaceholderText("默认 0.50")

        self.ed_weight_novelty = QLineEdit()
        self.ed_weight_novelty.setPlaceholderText("默认 0.30")

        self.ed_weight_recency = QLineEdit()
        self.ed_weight_recency.setPlaceholderText("默认 0.10")

        self.ed_weight_citation = QLineEdit()
        self.ed_weight_citation.setPlaceholderText("默认 0.05")

        self.cb_sentence_transformer_model = QComboBox()
        self.cb_sentence_transformer_model.addItems(SENTENCE_TRANSFORMER_MODEL_OPTIONS)

        self.ed_zh2en_cache_size = QLineEdit()
        self.ed_zh2en_cache_size.setPlaceholderText("默认 3（范围 1~20）")

        form.addRow("最终输出论文数量", self.ed_final_output)
        form.addRow("第一个Prompt默认max_results", self.ed_arxiv_api_default)
        form.addRow("arXiv API 输出论文数量", self.ed_arxiv_fetch)
        form.addRow("第二个Prompt截断数量", self.ed_second_prompt_truncate)
        form.addRow("权重 relevance", self.ed_weight_relevance)
        form.addRow("权重 novelty", self.ed_weight_novelty)
        form.addRow("权重 recency", self.ed_weight_recency)
        form.addRow("权重 citation", self.ed_weight_citation)
        form.addRow("语义筛选模型", self.cb_sentence_transformer_model)
        form.addRow("—— 中译英并行配置 ——", QLabel(""))
        form.addRow("中译英缓存译文条数", self.ed_zh2en_cache_size)
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
            self._arxiv_api_default_max_results = int(system_cfg.get("arxiv_api_default_max_results", 30))
        except Exception:
            self._arxiv_api_default_max_results = 30
        self._arxiv_api_default_max_results = max(5, min(300, self._arxiv_api_default_max_results))

        try:
            self._arxiv_fetch_max_results = int(system_cfg.get("arxiv_fetch_max_results", 40))
        except Exception:
            self._arxiv_fetch_max_results = 40
        self._arxiv_fetch_max_results = max(5, min(300, self._arxiv_fetch_max_results))

        try:
            self._second_prompt_truncate_count = int(system_cfg.get("second_prompt_truncate_count", 40))
        except Exception:
            self._second_prompt_truncate_count = 40
        self._second_prompt_truncate_count = max(5, min(200, self._second_prompt_truncate_count))

        try:
            self._weight_relevance = float(system_cfg.get("weight_relevance", 0.50))
        except Exception:
            self._weight_relevance = 0.50
        try:
            self._weight_novelty = float(system_cfg.get("weight_novelty", 0.25))
        except Exception:
            self._weight_novelty = 0.25
        try:
            self._weight_recency = float(system_cfg.get("weight_recency", 0.20))
        except Exception:
            self._weight_recency = 0.20
        try:
            self._weight_citation = float(system_cfg.get("weight_citation", 0.05))
        except Exception:
            self._weight_citation = 0.05

        selected_model = str(system_cfg.get("sentence_transformer_model", "BAAI/bge-large-en-v1.5") or "").strip()
        if selected_model not in SENTENCE_TRANSFORMER_MODEL_OPTIONS:
            selected_model = "BAAI/bge-large-en-v1.5"
        self._sentence_transformer_model = selected_model

        try:
            self._zh2en_translation_cache_size = int(system_cfg.get("zh2en_translation_cache_size", 3))
        except Exception:
            self._zh2en_translation_cache_size = 3
        self._zh2en_translation_cache_size = max(1, min(20, self._zh2en_translation_cache_size))

        self.ed_final_output.setText(str(self._final_output_paper_count))
        self.ed_arxiv_api_default.setText(str(self._arxiv_api_default_max_results))
        self.ed_arxiv_fetch.setText(str(self._arxiv_fetch_max_results))
        self.ed_second_prompt_truncate.setText(str(self._second_prompt_truncate_count))
        self.ed_weight_relevance.setText(f"{self._weight_relevance:.2f}")
        self.ed_weight_novelty.setText(f"{self._weight_novelty:.2f}")
        self.ed_weight_recency.setText(f"{self._weight_recency:.2f}")
        self.ed_weight_citation.setText(f"{self._weight_citation:.2f}")
        self.cb_sentence_transformer_model.setCurrentText(self._sentence_transformer_model)
        self.ed_zh2en_cache_size.setText(str(self._zh2en_translation_cache_size))

    def dump(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        system_cfg = settings.setdefault("system", {}) if isinstance(settings, dict) else {}
        if isinstance(system_cfg, dict):
            system_cfg["final_output_paper_count"] = self._final_output_paper_count
            system_cfg["arxiv_api_default_max_results"] = self._arxiv_api_default_max_results
            system_cfg["arxiv_fetch_max_results"] = self._arxiv_fetch_max_results
            system_cfg["second_prompt_truncate_count"] = self._second_prompt_truncate_count
            system_cfg["weight_relevance"] = round(self._weight_relevance, 4)
            system_cfg["weight_novelty"] = round(self._weight_novelty, 4)
            system_cfg["weight_recency"] = round(self._weight_recency, 4)
            system_cfg["weight_citation"] = round(self._weight_citation, 4)
            system_cfg["sentence_transformer_model"] = self._sentence_transformer_model
            system_cfg["zh2en_translation_cache_size"] = self._zh2en_translation_cache_size
        return settings

    def validate_or_warn(self, parent=None) -> bool:
        final_text = str(self.ed_final_output.text() or "").strip()
        api_default_text = str(self.ed_arxiv_api_default.text() or "").strip()
        fetch_text = str(self.ed_arxiv_fetch.text() or "").strip()
        second_truncate_text = str(self.ed_second_prompt_truncate.text() or "").strip()
        wr_text = str(self.ed_weight_relevance.text() or "").strip()
        wn_text = str(self.ed_weight_novelty.text() or "").strip()
        wre_text = str(self.ed_weight_recency.text() or "").strip()
        wc_text = str(self.ed_weight_citation.text() or "").strip()
        zh2en_cache_size_text = str(self.ed_zh2en_cache_size.text() or "").strip()

        try:
            final_count = int(final_text or "5")
        except Exception:
            QMessageBox.warning(parent, "提示", "最终输出论文数量必须是整数。")
            return False

        try:
            api_default_count = int(api_default_text or "30")
        except Exception:
            QMessageBox.warning(parent, "提示", "第一个Prompt默认max_results必须是整数。")
            return False

        try:
            fetch_count = int(fetch_text or "40")
        except Exception:
            QMessageBox.warning(parent, "提示", "arXiv API 输出论文数量必须是整数。")
            return False

        try:
            second_truncate_count = int(second_truncate_text or "40")
        except Exception:
            QMessageBox.warning(parent, "提示", "第二个Prompt截断数量必须是整数。")
            return False

        try:
            zh2en_cache_size = int(zh2en_cache_size_text or "3")
        except Exception:
            QMessageBox.warning(parent, "提示", "中译英缓存译文条数必须是整数。")
            return False

        if final_count < 1 or final_count > 50:
            QMessageBox.warning(parent, "提示", "最终输出论文数量范围应为 1~50。")
            return False

        if api_default_count < 5 or api_default_count > 300:
            QMessageBox.warning(parent, "提示", "第一个Prompt默认max_results范围应为 5~300。")
            return False

        if fetch_count < 5 or fetch_count > 300:
            QMessageBox.warning(parent, "提示", "arXiv API 输出论文数量范围应为 5~300。")
            return False

        if second_truncate_count < 5 or second_truncate_count > 200:
            QMessageBox.warning(parent, "提示", "第二个Prompt截断数量范围应为 5~200。")
            return False

        if fetch_count < final_count:
            QMessageBox.warning(parent, "提示", "arXiv API 输出论文数量不能小于最终输出论文数量。")
            return False

        if zh2en_cache_size < 1 or zh2en_cache_size > 20:
            QMessageBox.warning(parent, "提示", "中译英缓存译文条数范围应为 1~20。")
            return False

        try:
            wr = float(wr_text or "0.50")
            wn = float(wn_text or "0.25")
            wre = float(wre_text or "0.20")
            wc = float(wc_text or "0.05")
        except Exception:
            QMessageBox.warning(parent, "提示", "四个权重必须是数字。")
            return False

        weights = [wr, wn, wre, wc]
        if any(x < 0.0 for x in weights):
            QMessageBox.warning(parent, "提示", "四个权重必须为非负数。")
            return False

        total = sum(weights)
        if total <= 0.0:
            QMessageBox.warning(parent, "提示", "四个权重之和必须大于 0。")
            return False

        self._final_output_paper_count = final_count
        self._arxiv_api_default_max_results = api_default_count
        self._arxiv_fetch_max_results = fetch_count
        self._second_prompt_truncate_count = second_truncate_count
        self._weight_relevance = wr
        self._weight_novelty = wn
        self._weight_recency = wre
        self._weight_citation = wc
        self._zh2en_translation_cache_size = zh2en_cache_size
        selected_model = str(self.cb_sentence_transformer_model.currentText() or "").strip()
        if selected_model not in SENTENCE_TRANSFORMER_MODEL_OPTIONS:
            QMessageBox.warning(parent, "提示", "语义筛选模型无效，请重新选择。")
            return False
        self._sentence_transformer_model = selected_model
        return True
