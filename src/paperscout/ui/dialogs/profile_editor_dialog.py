from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QMessageBox,
    QFrame, QTabWidget, QWidget
)

from paperscout.config.settings import set_profile_agent_api_key, get_safe_str, PROVIDERS


class ProfileEditorDialog(QDialog):
    PROVIDERS: List[Tuple[str, str]] = [
        ("deepseek", "DeepSeek"),
        ("openai", "OpenAI"),
        ("google", "Gemini"),
        ("doubao", "豆包（Doubao）"),
    ]

    DEFAULT_MODELS: Dict[str, List[str]] = {
        "deepseek": ["deepseek-chat", "deepseek-reasoner"],
        "openai": ["gpt-4o-mini", "gpt-4.1"],
        "google": ["gemini-2.5-flash", "gemini-2.0-flash"],
        "doubao": [],
    }

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
        for m in self.DEFAULT_MODELS.get(provider, []):
            cmb_model.addItem(m)
        model = get_safe_str(cfg, "model", "")
        if model:
            if cmb_model.findText(model) >= 0:
                cmb_model.setCurrentText(model)
            else:
                cmb_model.addItem(model)
                cmb_model.setCurrentText(model)

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

        form.addRow("Model", cmb_model)
        form.addRow("API Key", ed_key)
        form.addRow("Base URL（可选）", ed_base)

        layout.addLayout(form)

        self._agent_ui[provider] = {
            "model": cmb_model,
            "api_key": ed_key,
            "base_url": ed_base,
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
            agent_cfg = {
                "model": get_safe_str({"m": ui["model"].currentText()}, "m", "").strip(),
                "base_url": get_safe_str({"b": ui["base_url"].text()}, "b", "").strip(),
                "api_key_keyring": "",  # 暂时为空，稍后通过 set_profile_agent_api_key 设置
            }
            if prov == "deepseek" and not agent_cfg["base_url"]:
                agent_cfg["base_url"] = "https://api.deepseek.com/v1"
            
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
