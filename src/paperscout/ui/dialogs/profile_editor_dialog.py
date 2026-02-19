from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QMessageBox,
    QFrame, QTabWidget, QWidget, QDoubleSpinBox, QSpinBox
)

from paperscout.config.settings import set_profile_agent_api_key, get_safe_str, PROVIDERS, PROVIDER_TUPLES, DEFAULT_MODELS


class ProfileEditorDialog(QDialog):
    PROVIDERS: List[Tuple[str, str]] = PROVIDER_TUPLES

    DEFAULT_MODELS: Dict[str, List[str]] = DEFAULT_MODELS

    @classmethod
    def _populate_model_combo(cls, combo: QComboBox, provider: str):
        combo.clear()
        for model_id in cls.DEFAULT_MODELS.get(provider, []):
            combo.addItem(model_id, userData=model_id)

    @staticmethod
    def _set_combo_model(combo: QComboBox, model_id: str):
        mid = str(model_id or "").strip()
        if not mid:
            combo.setCurrentText("")
            return
        idx = combo.findData(mid)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.addItem(mid, userData=mid)
            combo.setCurrentText(mid)

    @staticmethod
    def _get_combo_model(combo: QComboBox) -> str:
        model_id = combo.currentData()
        if model_id is not None:
            return str(model_id).strip()
        return str(combo.currentText() or "").strip()

    def __init__(self, parent=None, initial: Optional[Dict[str, Any]] = None, title: str = "编辑配置集"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(640, 520)

        self._initial = dict(initial or {})
        self._agent_ui: Dict[str, Dict[str, Any]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        tip = QLabel("此配置集同时包含四家模型配置（DeepSeek / OpenAI / Gemini / 豆包）。")
        tip.setStyleSheet("color:#666;")
        root.addWidget(tip)

        box = QFrame()
        box.setStyleSheet("QFrame{border:1px solid #eeeeee;border-radius:12px;background:#ffffff;}")
        root.addWidget(box, 1)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 14, 14, 14)
        bl.setSpacing(10)

        form_top = QFormLayout()
        form_top.setLabelAlignment(Qt.AlignLeft)
        form_top.setHorizontalSpacing(12)
        form_top.setVerticalSpacing(10)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("例如：四模型联动-默认配置")
        self.ed_name.setText(get_safe_str(self._initial, "name", ""))

        self.cmb_default = QComboBox()
        for key, name in self.PROVIDERS:
            self.cmb_default.addItem(name, userData=key)

        form_top.addRow("配置集名称", self.ed_name)
        form_top.addRow("主界面默认聊天使用", self.cmb_default)
        bl.addLayout(form_top)

        self.tabs = QTabWidget()
        bl.addWidget(self.tabs, 1)

        agents = (self._initial.get("agents") or {}) if isinstance(self._initial.get("agents"), dict) else {}
        default_agent = get_safe_str(self._initial, "default_agent", "deepseek")

        for prov, display in self.PROVIDERS:
            cfg = agents.get(prov, {}) if isinstance(agents.get(prov), dict) else {}
            tab = self._build_agent_tab(prov, cfg)
            self.tabs.addTab(tab, display)

        # set default agent selection
        self._set_default_agent(default_agent)

        # buttons
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_ok = QPushButton("确定")
        self.btn_ok.setDefault(True)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        root.addLayout(row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_ok)

    def _set_default_agent(self, provider_key: str):
        for i in range(self.cmb_default.count()):
            if self.cmb_default.itemData(i) == provider_key:
                self.cmb_default.setCurrentIndex(i)
                return

    def _build_agent_tab(self, provider: str, cfg: Dict[str, Any]) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        cmb_model = QComboBox()
        cmb_model.setEditable(True)
        self._populate_model_combo(cmb_model, provider)
        model = get_safe_str(cfg, "model", "")
        self._set_combo_model(cmb_model, model)

        ed_key = QLineEdit()
        ed_key.setEchoMode(QLineEdit.Password)
        # 优先显示 keyring 中的 key，否则显示 keyring_ref
        api_key = get_safe_str(cfg, "api_key", "")
        if not api_key and cfg.get("api_key_keyring"):
            # keyring 中有值但还未加载，显示 *** 掩码
            api_key = "***"
        ed_key.setText(api_key)

        ed_base = QLineEdit()
        ed_base.setPlaceholderText("可选：留空则使用默认/SDK默认")
        ed_base.setText(get_safe_str(cfg, "base_url", ""))

        spn_temp = QDoubleSpinBox()
        spn_temp.setRange(0.0, 2.0)
        spn_temp.setSingleStep(0.1)
        spn_temp.setDecimals(2)
        try:
            spn_temp.setValue(float(cfg.get("temperature", 0.2) or 0.2))
        except (TypeError, ValueError):
            spn_temp.setValue(0.2)

        spn_top_p = QDoubleSpinBox()
        spn_top_p.setRange(0.0, 1.0)
        spn_top_p.setSingleStep(0.1)
        spn_top_p.setDecimals(2)
        try:
            spn_top_p.setValue(float(cfg.get("top_p", 1.0) or 1.0))
        except (TypeError, ValueError):
            spn_top_p.setValue(1.0)

        spn_max_tokens = QSpinBox()
        spn_max_tokens.setRange(1, 65536)
        spn_max_tokens.setSingleStep(256)
        try:
            spn_max_tokens.setValue(int(cfg.get("max_tokens", 2048) or 2048))
        except (TypeError, ValueError):
            spn_max_tokens.setValue(2048)

        form.addRow("Model", cmb_model)
        form.addRow("API Key", ed_key)
        form.addRow("Base URL（可选）", ed_base)
        form.addRow("Temperature", spn_temp)
        form.addRow("Top P", spn_top_p)
        form.addRow("Max Tokens", spn_max_tokens)

        layout.addLayout(form)

        self._agent_ui[provider] = {
            "model": cmb_model,
            "api_key": ed_key,
            "base_url": ed_base,
            "temperature": spn_temp,
            "top_p": spn_top_p,
            "max_tokens": spn_max_tokens,
        }
        return w

    def _on_ok(self):
        name = get_safe_str({"name": self.ed_name.text()}, "name", "").strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写配置集名称。")
            return

        # default agent must have model
        default_agent = (self.cmb_default.currentData() or "deepseek").strip()
        ui = self._agent_ui.get(default_agent, {})
        model = (ui.get("model").currentText() if ui.get("model") else "") or ""
        if not model.strip():
            QMessageBox.warning(self, "提示", "主界面默认聊天使用的 provider 未填写 Model。")
            return

        self.accept()

    def result_profile(self, existing_id: Optional[str] = None) -> Dict[str, Any]:
        pid = get_safe_str({"id": existing_id or self._initial.get("id")}, "id", "").strip()
        if not pid:
            pid = f"p_{uuid4().hex[:8]}"

        agents: Dict[str, Any] = {}
        for prov, _ in self.PROVIDERS:
            ui = self._agent_ui[prov]
            raw_base = get_safe_str({"b": ui["base_url"].text()}, "b", "").strip()
            agent_cfg = {
                "model": self._get_combo_model(ui["model"]),
                "base_url": raw_base,
                "api_key_keyring": "",  # 暂时为空，稍后通过 set_profile_agent_api_key 设置
                "temperature": ui["temperature"].value(),
                "top_p": ui["top_p"].value(),
                "max_tokens": ui["max_tokens"].value(),
            }
            if prov == "deepseek" and not agent_cfg["base_url"]:
                agent_cfg["base_url"] = "https://api.deepseek.com"
            
            agents[prov] = agent_cfg

        profile = {
            "id": pid,
            "name": get_safe_str({"n": self.ed_name.text()}, "n", "").strip(),
            "default_agent": (self.cmb_default.currentData() or "deepseek").strip(),
            "agents": agents,
        }
        
        # 现在设置 API Keys 到 keyring
        for prov, _ in self.PROVIDERS:
            ui = self._agent_ui[prov]
            api_key = ui["api_key"].text().strip()
            # 跳过占位符 *** （表示 keyring 中已有值）
            if api_key and api_key != "***":
                set_profile_agent_api_key(profile, prov, api_key)
        
        return profile

    @staticmethod
    def create_profile(parent=None) -> Optional[Dict[str, Any]]:
        dlg = ProfileEditorDialog(parent=parent, initial=None, title="新建配置集（四模型）")
        if dlg.exec() == QDialog.Accepted:
            return dlg.result_profile()
        return None

    @staticmethod
    def edit_profile(initial: Dict[str, Any], parent=None) -> Optional[Dict[str, Any]]:
        dlg = ProfileEditorDialog(parent=parent, initial=initial, title="编辑配置集（四模型）")
        if dlg.exec() == QDialog.Accepted:
            return dlg.result_profile(existing_id=get_safe_str(initial, "id", ""))
        return None
