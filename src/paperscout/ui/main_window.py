from __future__ import annotations

import json
from typing import Dict, List

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QMessageBox, QInputDialog

from paperscout.config.settings import load_settings, save_settings
from paperscout.config.ui_state import (
    ensure_ui_state,
    list_threads,
    set_active_thread,
    add_thread,
    remove_legacy_default_threads,
)
from paperscout.ui.controllers.chat_controller import ChatController
from paperscout.ui.components.feature_sidebar import FeatureSidebar, FeatureItem
from paperscout.ui.components.chat_header import ChatHeader
from paperscout.ui.components.chat_view import ChatView
from paperscout.ui.components.composer import Composer
from paperscout.ui.dialogs.profile_editor_dialog import ProfileEditorDialog
from paperscout.ui.menus.model_menu import build_profile_menu
from paperscout.ui.settings.settings_window import SettingsWindow
from paperscout.services.runtime_context import runtime_store


class MainWindow(QMainWindow):
    NO_THREAD_SESSION_ID = "__no_thread__"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PaperScout")
        self.resize(1200, 720)

        self.settings = ensure_ui_state(load_settings())
        if remove_legacy_default_threads(self.settings):
            try:
                save_settings(self.settings)
            except Exception:
                pass
        self.chat = ChatController()
        self._init_timeout_ms = 300000  # 默认 5 分钟（可在设置页调整）
        self._reload_init_timeout()
        self._send_locked = False

        # keep refs to background threads / workers / relays (prevent GC)
        self._bg_threads: list = []
        self._refresh_pending = False

        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # -------- left --------
        left_frame = QFrame()
        left_frame.setObjectName("LeftPane")
        left_frame.setFixedWidth(300)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 仅保留一个顶层功能：爬取arxiv（后续可追加更多 FeatureItem）
        features = [
            FeatureItem(key="arxiv", name="爬取arxiv", meta="arXiv / 抓取 / 评估（后续接入）"),
            FeatureItem(key="zh2en", name="中译英", meta="中译英 / 会话初始化（后续接入）"),
        ]
        self.sidebar = FeatureSidebar(features)
        left_layout.addWidget(self.sidebar, 1)

        # -------- right --------
        right_frame = QFrame()
        right_frame.setObjectName("RightPane")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.header = ChatHeader("PaperScout")
        self.view = ChatView()
        self.composer = Composer()

        right_layout.addWidget(self.header, 0)
        right_layout.addWidget(self.view, 1)
        right_layout.addWidget(self.composer, 0)

        root_layout.addWidget(left_frame)
        root_layout.addWidget(right_frame, 1)

        # signals
        self.sidebar.thread_selected.connect(self.on_thread_selected)
        self.sidebar.thread_created.connect(self.on_thread_created)
        self.sidebar.thread_deleted.connect(self.on_thread_deleted)
        self.sidebar.feature_expanded_changed.connect(self.on_feature_expanded_changed)

        self.header.settings_clicked.connect(self.open_settings)
        self.composer.model_clicked.connect(self.open_profile_menu)
        self.composer.send_clicked.connect(self.on_send)

        self._apply_qss()
        self._load_sidebar_state()
        self._refresh()

    def _apply_qss(self):
        try:
            from importlib import resources
            qss = resources.files("paperscout.ui").joinpath("styles.qss").read_text(encoding="utf-8")
            self.setStyleSheet(qss)
        except Exception:
            pass

    def _reload_init_timeout(self):
        ui = (self.settings.get("ui", {}) or {}) if isinstance(self.settings, dict) else {}
        try:
            timeout_sec = int(ui.get("init_timeout_sec", 300))
        except Exception:
            timeout_sec = 300
        timeout_sec = max(60, min(1800, timeout_sec))
        self._init_timeout_ms = timeout_sec * 1000

    # ---------- settings helpers ----------
    def _llm(self) -> dict:
        return (self.settings.get("llm", {}) or {})

    def _profiles(self) -> List[Dict]:
        return list(self._llm().get("profiles", []) or [])

    def _active_profile_id(self) -> str:
        return (self._llm().get("active_profile_id") or "").strip()

    def _find_profile(self, pid: str) -> Dict:
        for p in self._profiles():
            if (p.get("id") or "").strip() == pid:
                return p
        return {}

    def _active_profile(self) -> Dict:
        ps = self._profiles()
        if not ps:
            return {}
        pid = self._active_profile_id()
        p = self._find_profile(pid)
        return p if p else ps[0]

    def _active_default_agent_info(self) -> tuple[str, str]:
        p = self._active_profile()
        default_agent = (p.get("default_agent") or "deepseek").strip()
        agents = (p.get("agents") or {}) if isinstance(p.get("agents"), dict) else {}
        model = (((agents.get(default_agent) or {}).get("model")) or "").strip()
        return default_agent, model

    # ---------- UI helpers ----------
    def current_context_name(self) -> str:
        _fkey, _tid, tname = self.sidebar.current_selection()
        return tname or "（未选择对话）"

    def _sync_composer_state(self):
        _fkey, tid, _tname = self.sidebar.current_selection()
        has_thread = bool((tid or "").strip())

        try:
            self.composer.input.setEnabled(has_thread)
            self.composer.btn_send.setEnabled(has_thread and (not self._send_locked))
            if has_thread:
                self.composer.input.setPlaceholderText("输入指令…")
            else:
                self.composer.input.setPlaceholderText("请先在左侧点击＋新建对话")
        except Exception:
            pass

    def _load_sidebar_state(self):
        # Build sidebar from persisted UI state
        ui = (self.settings.get("ui", {}) or {}) if isinstance(self.settings, dict) else {}
        features_state = (ui.get("features", {}) or {}) if isinstance(ui, dict) else {}

        threads_by = {}
        expanded = {}
        active = {}

        for feat in getattr(self.sidebar, "features", []) or []:
            fkey = feat.key
            fstate = features_state.get(fkey, {}) if isinstance(features_state, dict) else {}
            threads_by[fkey] = list_threads(self.settings, fkey)
            if isinstance(fstate, dict):
                expanded[fkey] = bool(fstate.get("expanded", True))
                active[fkey] = str(fstate.get("active_thread_id") or "").strip()

        self.sidebar.load(threads_by_feature=threads_by, expanded=expanded, active=active)

        # Sync chat session with active thread
        _fkey, tid, _tname = self.sidebar.current_selection()
        if tid:
            self.chat.set_session(tid)
        else:
            self.chat.set_session(self.NO_THREAD_SESSION_ID)
        self._sync_composer_state()

    def _refresh(self):
        """Coalesce rapid refresh calls into one per event-loop cycle."""
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self):
        self._refresh_pending = False
        self._sync_composer_state()
        p = self._active_profile()
        profile_name = (p.get("name") or "未命名配置集").strip()
        default_agent, model = self._active_default_agent_info()

        self.header.set_subtitle(
            f"当前：{profile_name} · 默认：{default_agent}/{model} · 对话：{self.current_context_name()}"
        )

        html = self.chat.render_html(
            self.current_context_name(),
            profile_name,
            session_id=self.chat.current_session_id(),
        )
        self.view.set_html_and_scroll_bottom(html)

    # ---------- handlers ----------
    def on_thread_selected(self, feature_key: str, thread_id: str, thread_name: str):
        set_active_thread(self.settings, feature_key, thread_id)
        try:
            save_settings(self.settings)
        except Exception:
            pass

        self.chat.set_session(thread_id)
        self.chat.set_meta("feature_key", feature_key, session_id=thread_id)
        self.chat.add("system", f"已切换对话：{thread_name}")
        self._sync_composer_state()
        self._refresh()

    def on_feature_expanded_changed(self, feature_key: str, expanded: bool):
        ui = self.settings.setdefault("ui", {})
        features = ui.setdefault("features", {}) if isinstance(ui, dict) else {}
        feature = features.setdefault(feature_key, {}) if isinstance(features, dict) else {}
        if isinstance(feature, dict):
            feature["expanded"] = bool(expanded)
        try:
            save_settings(self.settings)
        except Exception:
            pass

    def on_thread_created(self, feature_key: str, thread_id: str, thread_name: str):
        add_thread(self.settings, feature_key, thread_id, thread_name)
        try:
            save_settings(self.settings)
        except Exception:
            pass

        self._load_sidebar_state()

        # zh2en: create-and-chat directly (no popup, no init pipeline)
        if feature_key == "zh2en":
            original_input = (thread_name or "").strip() or "新对话"
            runtime_store.set_original_input(thread_id, original_input)

            self.chat.set_session(thread_id)
            self.chat.set_meta("feature_key", feature_key, session_id=thread_id)
            self.chat.set_meta("original_input", original_input, session_id=thread_id)
            self.chat.set_meta("init_state", "done", session_id=thread_id)
            # Keep default strategy context and cache fields without running init pipeline.
            self.chat.set_meta(
                "init_meta",
                {
                    "original_input": original_input,
                    "zh2en_init_reply": "",
                    "zh2en_translation_list": [],
                    "zh2en_latest_translation": "",
                    "init_errors": {},
                },
                session_id=thread_id,
            )
            self._sync_composer_state()
            self._refresh()
            return

        original_input, ok = QInputDialog.getMultiLineText(
            self,
            "初始化原始输入",
            "请输入本会话的原始需求（用于后续摘要对比）：",
            thread_name,
        )
        if not ok:
            original_input = thread_name
        original_input = (original_input or "").strip() or thread_name

        runtime_store.set_original_input(thread_id, original_input)

        self.chat.set_session(thread_id)
        self.chat.set_meta("feature_key", feature_key, session_id=thread_id)
        self.chat.set_meta("original_input", original_input, session_id=thread_id)
        self.chat.set_meta("init_state", "running", session_id=thread_id)
        self._sync_composer_state()
        self._refresh()

        from paperscout.ui.workers.init_pipeline_worker import start_init_pipeline

        def _on_progress(msg: str):
            self.chat.upsert_system_line(msg, session_id=thread_id, key="init_progress_line_idx")
            self._refresh()

        def _on_ok(summary: str, data: dict):
            state = str(self.chat.get_meta("init_state", "", session_id=thread_id) or "").strip()
            if state == "timeout":
                self.chat.add("system", "初始化结果迟到返回，已忽略。", session_id=thread_id)
                self._refresh()
                return

            self.chat.upsert_system_line("初始化 6/6", session_id=thread_id, key="init_progress_line_idx")

            # 保存 init 信息到 session_meta，后续每次发送会注入
            init_meta = {
                "openai_init_reply": (data or {}).get("openai_init_reply", ""),
                "arxiv_api_payload": (data or {}).get("arxiv_api_payload", {}),
                "arxiv_fetch_config": (data or {}).get("arxiv_fetch_config", {}),
                "arxiv_selected_papers": (data or {}).get("arxiv_selected_papers", []),
                "arxiv_selected_count": (data or {}).get("arxiv_selected_count", 0),
                "arxiv_compare_result": (data or {}).get("arxiv_compare_result", {}),
                "arxiv_organized_report": (data or {}).get("arxiv_organized_report", ""),
                "original_input": original_input,
                "init_errors": (data or {}).get("init_errors", {}),
            }
            self.chat.set_meta("init_meta", init_meta, session_id=thread_id)
            self.chat.set_meta("init_state", "done", session_id=thread_id)

            # 仅输出第三个 prompt 的最终整理结果；不展示第一、第二个 prompt 的结果
            final_report = str(init_meta.get("arxiv_organized_report") or "").strip() or (summary or "初始化完成。")
            system_cfg = (self.settings.get("system", {}) or {}) if isinstance(self.settings, dict) else {}
            if not isinstance(system_cfg, dict):
                system_cfg = {}

            api_default = int(system_cfg.get("arxiv_api_default_max_results", 40) or 40)
            second_limit = int(system_cfg.get("second_prompt_truncate_count", 80) or 80)
            arxiv_output = int(system_cfg.get("arxiv_fetch_max_results", 60) or 60)

            compare_result = init_meta.get("arxiv_compare_result") if isinstance(init_meta.get("arxiv_compare_result"), dict) else {}
            used_model = str(compare_result.get("used_model") or "").strip() or "未获取"
            fetch_cfg = init_meta.get("arxiv_fetch_config") if isinstance(init_meta.get("arxiv_fetch_config"), dict) else {}
            semantic_model = str(fetch_cfg.get("sentence_transformer_model") or "").strip()
            if not semantic_model:
                semantic_model = str(system_cfg.get("sentence_transformer_model") or "").strip() or "未获取"

            header_line = (
                f"参数：max_results默认={api_default}；第二Prompt截断={second_limit}；"
                f"arXiv输出数量={arxiv_output}；第二Prompt模型={used_model}；语义筛选模型={semantic_model}"
            )
            final_report = f"{header_line}\n\n{final_report}"
            self.chat.add("assistant", final_report, session_id=thread_id)

            # 如果有错误也提示一下
            errs = init_meta.get("init_errors") or {}
            if isinstance(errs, dict) and errs:
                self.chat.add("system", f"初始化提示：{errs}", session_id=thread_id)

            self._refresh()

        def _on_err(err: str):
            self.chat.set_meta("init_state", "failed", session_id=thread_id)
            self.chat.upsert_system_line("初始化 失败", session_id=thread_id, key="init_progress_line_idx")
            self.chat.add("assistant", f"初始化失败：{err}", session_id=thread_id)
            self._refresh()

        def _on_init_timeout():
            state = str(self.chat.get_meta("init_state", "", session_id=thread_id) or "").strip()
            if state == "running":
                self.chat.set_meta("init_state", "timeout", session_id=thread_id)
                self.chat.upsert_system_line("初始化 超时", session_id=thread_id, key="init_progress_line_idx")
                self.chat.add(
                    "assistant",
                    "初始化超时，已自动结束初始化。你可以直接继续聊天；如需重试请新建会话。",
                    session_id=thread_id,
                )
                self._refresh()

        th, worker, relay = start_init_pipeline(
            settings=self.settings,
            feature_key=feature_key,
            thread_id=thread_id,
            thread_name=thread_name,
            original_input=original_input,
            on_progress=_on_progress,
            on_ok=_on_ok,
            on_err=_on_err,
        )
        # 必须同时保持 thread、worker、relay 的 Python 引用，否则 GC 会提前回收导致段错误
        self._bg_threads.append((th, worker, relay))
        try:
            th.finished.connect(self._cleanup_finished_threads)
        except Exception:
            pass
        QTimer.singleShot(self._init_timeout_ms, _on_init_timeout)

    def _cleanup_finished_threads(self):
        """Remove references to threads that have finished and schedule deletion."""
        alive = []
        for item in self._bg_threads:
            if not isinstance(item, tuple):
                continue
            th = item[0]
            if th.isRunning():
                alive.append(item)
            else:
                # Schedule QObject deletion for thread, worker, and relay
                for obj in item:
                    try:
                        obj.deleteLater()
                    except Exception:
                        pass
        self._bg_threads = alive


    def on_thread_deleted(self, feature_key: str, thread_id: str):
        ensure_ui_state(self.settings)

        # Clean up runtime cache for this thread
        runtime_store.remove_thread(thread_id)

        ui = self.settings.setdefault("ui", {})
        features = ui.setdefault("features", {})
        f = features.setdefault(feature_key, {})
        threads = f.get("threads", []) if isinstance(f, dict) else []
        if not isinstance(threads, list):
            return

        threads = [
            t for t in threads
            if not (isinstance(t, dict) and str(t.get("id") or "").strip() == thread_id)
        ]

        f["threads"] = threads
        if threads:
            f["active_thread_id"] = str(threads[0].get("id") or "").strip()
        else:
            f["active_thread_id"] = ""

        try:
            save_settings(self.settings)
        except Exception:
            pass

        self._load_sidebar_state()
        _fkey, tid, tname = self.sidebar.current_selection()
        if tid:
            self.chat.set_session(tid)
            self.chat.add("system", f"已删除对话并切换：{tname}")
        else:
            self.chat.set_session(self.NO_THREAD_SESSION_ID)
        self._sync_composer_state()
        self._refresh()

    def on_send(self, raw_text: str):
        raw_text = (raw_text or "").strip()
        if not raw_text:
            return

        current_feature, tid, _name = self.sidebar.current_selection()
        if not tid:
            QMessageBox.information(self, "提示", "请先在左侧点击＋新建对话。")
            self._sync_composer_state()
            return

        # 当前会话
        sid = str(tid).strip()
        self.chat.set_session(sid)
        feature_key = str(self.chat.get_meta("feature_key", "", session_id=sid) or "").strip()
        if not feature_key:
            feature_key = (current_feature or "arxiv").strip() or "arxiv"
            self.chat.set_meta("feature_key", feature_key, session_id=sid)

        # 1) 先把用户消息显示出来
        self.chat.add("user", raw_text, session_id=sid)
        self._refresh()

        # 2) 组装历史
        history = []
        for m in self.chat.messages(session_id=sid):
            if feature_key == "zh2en":
                if m.role in ("user", "assistant"):
                    history.append({"role": m.role, "content": m.text})
            elif m.role in ("user", "assistant"):
                history.append({"role": m.role, "content": m.text})

        # 3) 取 init meta
        init_meta = self.chat.get_meta("init_meta", {}, session_id=sid) or {}

        # 防止连点
        self._send_locked = True
        self._sync_composer_state()

        def _on_progress(msg: str):
            self.chat.add("system", msg, session_id=sid)
            self._refresh()

        def _on_ok(final_answer: str):
            self.chat.add("assistant", final_answer, session_id=sid)
            self._send_locked = False
            self._sync_composer_state()
            self._refresh()

        def _on_ok_zh2en(final_answer: str, updated_meta: dict):
            current_meta = self.chat.get_meta("init_meta", {}, session_id=sid) or {}
            merged_meta = dict(current_meta) if isinstance(current_meta, dict) else {}
            if isinstance(updated_meta, dict) and updated_meta:
                merged_meta.update(updated_meta)
                self.chat.set_meta("init_meta", merged_meta, session_id=sid)
            self.chat.add("assistant", final_answer, session_id=sid)
            self._send_locked = False
            self._sync_composer_state()
            self._refresh()

        def _on_err(err: str):
            prefix = "（中译英对话失败）" if feature_key == "zh2en" else "（OpenAI 对话失败）"
            self.chat.add("assistant", f"{prefix}{err}", session_id=sid)
            self._send_locked = False
            self._sync_composer_state()
            self._refresh()

        try:
            if feature_key == "zh2en":
                from paperscout.ui.workers.zh2en_chat_worker import start_zh2en_chat
                th, worker, relay = start_zh2en_chat(
                    settings=self.settings,
                    history=history[:-1],
                    user_text=raw_text,
                    init_meta=init_meta,
                    on_progress=_on_progress,
                    on_ok=_on_ok_zh2en,
                    on_err=_on_err,
                )
            else:
                from paperscout.ui.workers.dual_chat_worker import start_dual_chat
                th, worker, relay = start_dual_chat(
                    settings=self.settings,
                    history=history[:-1],      # 去掉刚刚加入的用户消息，worker里会再附上
                    user_text=raw_text,
                    init_meta=init_meta,
                    on_progress=_on_progress,
                    on_ok=_on_ok,
                    on_err=_on_err,
                )
        except Exception as e:
            self._send_locked = False
            self._sync_composer_state()
            self.chat.add("assistant", f"（启动对话失败）{e}", session_id=sid)
            self._refresh()
            return
        # 必须同时保持 thread、worker、relay 的 Python 引用
        self._bg_threads.append((th, worker, relay))
        try:
            th.finished.connect(self._cleanup_finished_threads)
        except Exception:
            pass


    def open_profile_menu(self):
        profiles = self._profiles()
        if not profiles:
            QMessageBox.warning(self, "提示", "未找到任何配置集，请在设置中新增。")
            return

        current_id = self._active_profile_id() or (profiles[0].get("id") or "").strip()

        def persist():
            try:
                save_settings(self.settings)
            except Exception:
                pass

        def on_select(pid: str):
            if not pid:
                return
            if pid == self._active_profile_id():
                return
            self.settings.setdefault("llm", {})
            self.settings["llm"]["active_profile_id"] = pid
            persist()
            self.chat.add("system", f"已切换配置集：{self._find_profile(pid).get('name', pid)}")
            self._refresh()

        def on_create():
            new_profile = ProfileEditorDialog.create_profile(self)
            if not new_profile:
                return
            llm = self.settings.setdefault("llm", {})
            llm.setdefault("profiles", [])
            llm["profiles"].append(new_profile)
            llm["active_profile_id"] = new_profile["id"]
            persist()
            self.chat.add("system", f"已创建并切换：{new_profile.get('name', new_profile['id'])}")
            self._refresh()

        def on_edit(pid: str):
            p = self._find_profile(pid)
            if not p:
                return
            updated = ProfileEditorDialog.edit_profile(p, parent=self)
            if not updated:
                return
            llm = self.settings.setdefault("llm", {})
            ps = llm.get("profiles", []) or []
            for i, x in enumerate(ps):
                if (x.get("id") or "").strip() == pid:
                    ps[i] = updated
                    break
            llm["profiles"] = ps
            persist()
            self.chat.add("system", f"已更新：{updated.get('name', pid)}")
            self._refresh()

        def on_delete(pid: str):
            ps = self._profiles()
            if len(ps) <= 1:
                QMessageBox.information(self, "提示", "至少保留一个配置集，无法删除。")
                return

            p = self._find_profile(pid)
            name = (p.get("name") or pid).strip()
            ret = QMessageBox.question(self, "确认删除", f"确定删除“{name}”吗？")
            if ret != QMessageBox.StandardButton.Yes:
                return

            llm = self.settings.setdefault("llm", {})
            llm["profiles"] = [x for x in ps if (x.get("id") or "").strip() != pid]
            if (llm.get("active_profile_id") or "").strip() == pid:
                llm["active_profile_id"] = (llm["profiles"][0].get("id") or "").strip()
            persist()
            self.chat.add("system", f"已删除：{name}")
            self._refresh()

        menu = build_profile_menu(
            parent=self,
            current_profile_id=current_id,
            profiles=profiles,
            on_select=on_select,
            on_create=on_create,
            on_edit=on_edit,
            on_delete=on_delete,
        )
        menu.exec(self.composer.btn_model.mapToGlobal(self.composer.btn_model.rect().bottomLeft()))

    def open_settings(self):
        dlg = SettingsWindow(self)
        dlg.settings_saved.connect(self.on_settings_saved)
        dlg.exec()

    def on_settings_saved(self, settings: dict):
        self.settings = ensure_ui_state(settings)
        self._reload_init_timeout()
        self._load_sidebar_state()
        self.chat.add("system", "设置已保存。")
        self._refresh()
