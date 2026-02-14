from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QListWidget,
    QListWidgetItem, QPushButton, QMessageBox, QFormLayout, QLineEdit,
    QComboBox, QTabWidget
)

from paperscout.ui.dialogs.profile_editor_dialog import ProfileEditorDialog
from paperscout.config.settings import (
    get_safe_str, set_profile_agent_api_key, get_profile_agent_info, PROVIDERS
)


class LLMPage(QWidget):
    PROVIDERS = [
        ("deepseek", "DeepSeek"),
        ("openai", "OpenAI"),
        ("google", "Gemini"),
        ("doubao", "豆包（Doubao）"),
    ]

    DEFAULT_MODELS = {
        "deepseek": ["deepseek-chat", "deepseek-reasoner"],
        "openai": ["gpt-4o-mini", "gpt-4.1"],
        "google": ["gemini-2.5-flash", "gemini-2.0-flash"],
        "doubao": [],
    }

    @staticmethod
    def _normalize_base_url(provider: str, base_url: str) -> str:
        url = str(base_url or "").strip()
        if not url:
            return ""
        if provider in ("openai", "deepseek", "google", "doubao"):
            p = urlparse(url)
            path = (p.path or "").strip()
            if path in ("", "/"):
                return url.rstrip("/") + "/v1"
        return url

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._profiles: List[Dict[str, Any]] = []
        self._active_profile_id: str = ""
        self._current_profile_id: Optional[str] = None
        self._agent_ui: Dict[str, Dict[str, Any]] = {}
        self._init_timeout_sec: int = 300

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("AI 模型配置（四模型联动）")
        title.setStyleSheet("font-weight:700; font-size:14px;")
        root.addWidget(title)

        tip = QLabel("每个“配置集”同时包含 DeepSeek / OpenAI / Gemini / 豆包 四套配置，供后续多步骤任务联动调用。")
        tip.setStyleSheet("color:#666;")
        root.addWidget(tip)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        # Left
        left = QFrame()
        left.setStyleSheet("QFrame{border:1px solid #eeeeee;border-radius:12px;background:#ffffff;}")
        left.setFixedWidth(320)
        body.addWidget(left, 0)

        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(10)

        self.lbl_active = QLabel("当前使用：-")
        self.lbl_active.setStyleSheet("font-weight:600;")
        ll.addWidget(self.lbl_active)

        self.list_profiles = QListWidget()
        self.list_profiles.setSpacing(4)
        ll.addWidget(self.list_profiles, 1)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("新增")
        self.btn_delete = QPushButton("删除")
        self.btn_set_active = QPushButton("设为当前")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_set_active)
        ll.addLayout(btn_row)

        # Right
        right = QFrame()
        right.setStyleSheet("QFrame{border:1px solid #eeeeee;border-radius:12px;background:#ffffff;}")
        body.addWidget(right, 1)

        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.setSpacing(10)

        self.lbl_editing = QLabel("编辑：-")
        self.lbl_editing.setStyleSheet("font-weight:700;")
        rl.addWidget(self.lbl_editing)

        top_form = QFormLayout()
        top_form.setLabelAlignment(Qt.AlignLeft)
        top_form.setHorizontalSpacing(12)
        top_form.setVerticalSpacing(10)

        self.ed_name = QLineEdit()
        self.cmb_default = QComboBox()
        for k, name in self.PROVIDERS:
            self.cmb_default.addItem(name, userData=k)

        self.ed_init_timeout = QLineEdit()
        self.ed_init_timeout.setPlaceholderText("默认 300（范围 60~1800）")

        top_form.addRow("配置集名称", self.ed_name)
        top_form.addRow("主界面默认聊天使用", self.cmb_default)
        top_form.addRow("初始化超时（秒）", self.ed_init_timeout)
        rl.addLayout(top_form)

        self.tabs = QTabWidget()
        rl.addWidget(self.tabs, 1)

        for prov, display in self.PROVIDERS:
            tab = self._build_agent_tab(prov, display)
            self.tabs.addTab(tab, display)

        rl.addStretch(1)

        # signals
        self.list_profiles.currentItemChanged.connect(self._on_profile_selected)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_set_active.clicked.connect(self._on_set_active)

    def _build_agent_tab(self, provider: str, display: str) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 10, 10, 10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        cmb_model = QComboBox()
        cmb_model.setEditable(True)
        for m in self.DEFAULT_MODELS.get(provider, []):
            cmb_model.addItem(m)

        ed_key = QLineEdit()
        ed_key.setEchoMode(QLineEdit.Password)

        ed_base = QLineEdit()
        ed_base.setPlaceholderText("可选：留空则使用默认/SDK默认")

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

    # ------------------------
    # load/dump
    # ------------------------
    def load(self, settings: Dict[str, Any]):
        self._syncing = True
        try:
            llm = (settings.get("llm", {}) or {})
            ui = (settings.get("ui", {}) or {}) if isinstance(settings, dict) else {}
            self._profiles = list(llm.get("profiles", []) or [])
            self._active_profile_id = (llm.get("active_profile_id") or "").strip()
            try:
                self._init_timeout_sec = int(ui.get("init_timeout_sec", 300))
            except Exception:
                self._init_timeout_sec = 300
            self._init_timeout_sec = max(60, min(1800, self._init_timeout_sec))
            self.ed_init_timeout.setText(str(self._init_timeout_sec))

            if not self._profiles:
                QMessageBox.information(self, "提示", "未找到配置集，将创建一个默认配置集。")
                p = ProfileEditorDialog.create_profile(self)
                if p:
                    self._profiles = [p]
                    self._active_profile_id = p["id"]

            if not self._active_profile_id or not any((p.get("id") or "").strip() == self._active_profile_id for p in self._profiles):
                self._active_profile_id = (self._profiles[0].get("id") or "").strip()

            self._rebuild_list(select_id=self._active_profile_id)
            self._update_active_label()
        finally:
            self._syncing = False

    def dump(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        self._apply_editor_to_current()
        llm = settings.setdefault("llm", {})
        llm["profiles"] = self._profiles
        llm["active_profile_id"] = self._active_profile_id
        ui = settings.setdefault("ui", {}) if isinstance(settings, dict) else {}
        if isinstance(ui, dict):
            ui["init_timeout_sec"] = self._init_timeout_sec
        return settings

    def validate_or_warn(self, parent=None) -> bool:
        self._apply_editor_to_current()
        if not self._profiles:
            QMessageBox.warning(parent, "提示", "至少需要一个配置集。")
            return False
        if not self._active_profile_id or not any(get_safe_str(p, "id") == self._active_profile_id for p in self._profiles):
            QMessageBox.warning(parent, "提示", "当前使用的配置集无效，请重新选择。")
            return False

        # 初始化超时校验（秒）
        timeout_text = str(self.ed_init_timeout.text() or "").strip()
        try:
            timeout_sec = int(timeout_text or "300")
        except Exception:
            QMessageBox.warning(parent, "提示", "初始化超时（秒）必须是整数。")
            return False
        if timeout_sec < 60 or timeout_sec > 1800:
            QMessageBox.warning(parent, "提示", "初始化超时（秒）范围应为 60~1800。")
            return False
        self._init_timeout_sec = timeout_sec

        problems: List[str] = []

        ids = [get_safe_str(p, "id") for p in self._profiles]
        names = [get_safe_str(p, "name") for p in self._profiles]

        if len({x for x in ids if x}) != len([x for x in ids if x]):
            problems.append("配置集 ID 存在重复，请删除冲突项后再保存。")

        if any(not x.strip() for x in names):
            problems.append("存在空的配置集名称，请为每个配置集填写名称。")
        elif len({x.strip().lower() for x in names}) != len(names):
            problems.append("配置集名称存在重复，请修改为唯一名称。")

        # 仅对“当前激活配置”做必要校验，避免未启用配置导致误报
        active = self._find_profile(self._active_profile_id)
        active_name = get_safe_str(active, "name", self._active_profile_id)
        active_default = get_safe_str(active, "default_agent", "openai")
        active_agents = active.get("agents") if isinstance(active.get("agents"), dict) else {}
        if active_default not in active_agents:
            problems.append(f"当前配置集“{active_name}”的默认 provider（{active_default}）不存在。")
        else:
            active_agent_info = get_profile_agent_info(active, active_default)
            active_model = get_safe_str(active_agent_info, "model", "").strip()
            active_base_url = self._normalize_base_url(
                active_default,
                get_safe_str(active_agent_info, "base_url", "").strip(),
            )
            active_api_key = get_safe_str(active_agent_info, "api_key", "").strip()

            if not active_model:
                problems.append(f"当前配置集“{active_name}”的默认 provider（{active_default}）未填写 Model。")

            if active_base_url:
                u = urlparse(active_base_url)
                if u.scheme not in ("http", "https") or not u.netloc:
                    problems.append(f"当前配置集“{active_name}”的默认 provider（{active_default}）Base URL 不合法：{active_base_url}")

            if not active_api_key:
                problems.append(f"当前配置集“{active_name}”的默认 provider（{active_default}）API Key 为空。")

            # 轻量可用性探测（仅在基础字段完整时执行）
            if active_api_key and active_model and not problems:
                ok, reason = self._check_provider_model_support(
                    provider=active_default,
                    base_url=active_base_url,
                    api_key=active_api_key,
                    model=active_model,
                )
                if not ok:
                    problems.append(
                        f"当前配置集“{active_name}”的默认 provider（{active_default}）模型探测失败：{reason}"
                    )

        if problems:
            msg = "保存失败，请先修正以下问题：\n\n- " + "\n- ".join(problems[:12])
            if len(problems) > 12:
                msg += f"\n\n（其余 {len(problems)-12} 项未展示）"
            QMessageBox.warning(parent, "配置冲突或输入不合理", msg)
            return False

        return True

    def _check_provider_model_support(self, provider: str, base_url: str, api_key: str, model: str) -> tuple[bool, str]:
        """Best-effort check whether provider endpoint supports the target model."""
        try:
            from openai import OpenAI
        except Exception as e:
            return False, f"缺少 openai 依赖：{e}"

        try:
            client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=10.0)

            # 优先使用 models.list()（成本低）
            try:
                resp = client.models.list()
                data = getattr(resp, "data", None)
                if isinstance(data, list):
                    model_ids = {str(getattr(x, "id", "") or "").strip() for x in data}
                    if model in model_ids:
                        return True, "ok"
            except Exception:
                # 某些网关不支持 models.list，降级到一次最小 chat 校验
                pass

            try:
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
                return True, "ok"
            except Exception as e:
                prefix = f"provider={provider}, base_url={base_url or '官方默认'}"
                return False, f"{prefix}，探测失败：{e}"

        except Exception as e:
            return False, str(e)

    # ------------------------
    # internals
    # ------------------------
    def _find_profile(self, pid: str) -> Dict[str, Any]:
        for p in self._profiles:
            if get_safe_str(p, "id") == pid:
                return p
        return {}

    def _rebuild_list(self, select_id: Optional[str] = None):
        self.list_profiles.blockSignals(True)
        self.list_profiles.clear()

        for p in self._profiles:
            pid = get_safe_str(p, "id")
            name = get_safe_str(p, "name", pid or "未命名配置集")
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, pid)
            self.list_profiles.addItem(item)

        selected_pid: Optional[str] = None
        if select_id:
            for i in range(self.list_profiles.count()):
                it = self.list_profiles.item(i)
                if it.data(Qt.UserRole) == select_id:
                    self.list_profiles.setCurrentItem(it)
                    selected_pid = it.data(Qt.UserRole)
                    break
            if selected_pid is None and self.list_profiles.count() > 0:
                self.list_profiles.setCurrentRow(0)
                it = self.list_profiles.currentItem()
                selected_pid = it.data(Qt.UserRole) if it else None
        else:
            if self.list_profiles.count() > 0:
                self.list_profiles.setCurrentRow(0)
                it = self.list_profiles.currentItem()
                selected_pid = it.data(Qt.UserRole) if it else None

        self.list_profiles.blockSignals(False)

        # list 构建时信号被 block，不会自动触发右侧编辑器刷新；这里手动同步
        if selected_pid:
            self._current_profile_id = selected_pid
            self._load_profile_to_editor(self._find_profile(selected_pid))

    def _update_active_label(self):
        p = self._find_profile(self._active_profile_id)
        name = get_safe_str(p, "name", self._active_profile_id or "-")
        default_agent = get_safe_str(p, "default_agent", "deepseek")
        model = get_safe_str(get_profile_agent_info(p, default_agent), "model", "")
        self.lbl_active.setText(f"当前使用：{name} · 默认：{default_agent}/{model}")

    def _load_profile_to_editor(self, p: Dict[str, Any]):
        self._syncing = True
        try:
            self.ed_name.setText(get_safe_str(p, "name", ""))
            default_agent = get_safe_str(p, "default_agent", "deepseek")
            for i in range(self.cmb_default.count()):
                if self.cmb_default.itemData(i) == default_agent:
                    self.cmb_default.setCurrentIndex(i)
                    break

            agents = (p.get("agents") or {}) if isinstance(p.get("agents"), dict) else {}
            for prov, _ in self.PROVIDERS:
                cfg = agents.get(prov, {}) if isinstance(agents.get(prov), dict) else {}
                ui = self._agent_ui[prov]

                model = get_safe_str(cfg, "model", "")
                ui["model"].blockSignals(True)
                # keep existing items + ensure selected
                if model:
                    if ui["model"].findText(model) >= 0:
                        ui["model"].setCurrentText(model)
                    else:
                        ui["model"].addItem(model)
                        ui["model"].setCurrentText(model)
                else:
                    ui["model"].setCurrentText("")
                ui["model"].blockSignals(False)

                ui["base_url"].setText(get_safe_str(cfg, "base_url", ""))

                # 加载 API Key：有 key 就显示占位符 ***，防止每次保存重复存储
                resolved_key = get_profile_agent_info({"agents": {prov: cfg}}, prov).get("api_key", "")
                has_keyring = bool(get_safe_str(cfg, "api_key_keyring", ""))
                if resolved_key or has_keyring:
                    ui["api_key"].setText("***")
                else:
                    ui["api_key"].setText("")

            self.lbl_editing.setText(f"编辑：{get_safe_str(p, 'name', p.get('id', '-')).strip()}")
        finally:
            self._syncing = False

    def _apply_editor_to_current(self):
        if not self._current_profile_id:
            return
        p = self._find_profile(self._current_profile_id)
        if not p:
            return

        p["name"] = get_safe_str({"n": self.ed_name.text()}, "n", "").strip() or get_safe_str(p, "name", "未命名配置集")
        p["default_agent"] = (self.cmb_default.currentData() or "deepseek").strip()

        p.setdefault("agents", {})
        agents = p["agents"] if isinstance(p["agents"], dict) else {}
        
        # 第一遍：更新 model / base_url，保留旧的 api_key_keyring
        for prov, _ in self.PROVIDERS:
            ui = self._agent_ui[prov]
            old_cfg = agents.get(prov, {}) if isinstance(agents.get(prov), dict) else {}
            agents[prov] = {
                "model": get_safe_str({"m": ui["model"].currentText()}, "m", "").strip(),
                "base_url": self._normalize_base_url(
                    prov,
                    get_safe_str({"b": ui["base_url"].text()}, "b", "").strip(),
                ),
                "api_key_keyring": old_cfg.get("api_key_keyring", ""),  # 保留旧的 keyring 引用
            }
            if prov == "deepseek" and not agents[prov]["base_url"]:
                agents[prov]["base_url"] = "https://api.deepseek.com/v1"

        # 确保 p["agents"] 引用正确的 agents dict
        p["agents"] = agents
        
        # 第二遍：处理 API Key 更新（此时 p["agents"] 已经是最新结构）
        for prov, _ in self.PROVIDERS:
            ui = self._agent_ui[prov]
            api_key_input = ui["api_key"].text().strip()
            if api_key_input and api_key_input != "***":
                # 用户输入了新的 API Key
                set_profile_agent_api_key(p, prov, api_key_input)
                # 清空输入框（表示已保存）
                ui["api_key"].setText("***")

        # update list item name
        for i in range(self.list_profiles.count()):
            it = self.list_profiles.item(i)
            if it.data(Qt.UserRole) == self._current_profile_id:
                it.setText(p["name"])
                break

        self._update_active_label()

    # ------------------------
    # slots
    # ------------------------
    def _on_profile_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if self._syncing:
            return
        self._apply_editor_to_current()

        if not current:
            self._current_profile_id = None
            return

        pid = current.data(Qt.UserRole)
        self._current_profile_id = pid
        self._load_profile_to_editor(self._find_profile(pid))

    def _on_add(self):
        self._apply_editor_to_current()
        p = ProfileEditorDialog.create_profile(self)
        if not p:
            return
        self._profiles.append(p)
        self._active_profile_id = p["id"]
        self._rebuild_list(select_id=p["id"])
        self._update_active_label()

    def _on_delete(self):
        if len(self._profiles) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个配置集，无法删除。")
            return
        it = self.list_profiles.currentItem()
        if not it:
            return
        pid = it.data(Qt.UserRole)
        name = get_safe_str(self._find_profile(pid), "name", pid).strip()
        ret = QMessageBox.question(self, "确认删除", f'确定删除"{name}"吗？')
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._profiles = [x for x in self._profiles if get_safe_str(x, "id") != pid]
        if self._active_profile_id == pid:
            self._active_profile_id = get_safe_str(self._profiles[0], "id", "")
        self._rebuild_list(select_id=self._active_profile_id)
        self._update_active_label()

    def _on_set_active(self):
        self._apply_editor_to_current()
        it = self.list_profiles.currentItem()
        if not it:
            return
        pid = it.data(Qt.UserRole)
        self._active_profile_id = pid
        self._update_active_label()
