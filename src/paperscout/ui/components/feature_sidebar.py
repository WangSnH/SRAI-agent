from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QInputDialog,
    QMessageBox,
)


@dataclass
class FeatureItem:
    key: str
    name: str
    meta: str = ""


class FeatureSidebar(QWidget):
    """Left sidebar with collapsible top-level features and sub-chats."""

    thread_selected = Signal(str, str, str)  # feature_key, thread_id, thread_name
    thread_created = Signal(str, str, str)   # feature_key, thread_id, thread_name
    thread_deleted = Signal(str, str)        # feature_key, thread_id
    feature_expanded_changed = Signal(str, bool)  # feature_key, expanded

    ROLE_KIND = Qt.UserRole
    ROLE_FEATURE = Qt.UserRole + 1
    ROLE_THREAD = Qt.UserRole + 2

    def __init__(self, features: List[FeatureItem], parent=None):
        super().__init__(parent)
        self.features = features
        self._active_threads: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("功能 / Features")
        title.setObjectName("LeftTitle")

        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("搜索对话…")
        self.search.setClearButtonEnabled(True)

        self.tree = QTreeWidget()
        self.tree.setObjectName("TaskList")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        layout.addWidget(title)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)

        self.search.textChanged.connect(self._filter)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)

    def load(self, threads_by_feature: dict[str, List[dict]], expanded: Optional[dict[str, bool]] = None,
             active: Optional[dict[str, str]] = None):
        """Populate tree.

        Args:
            threads_by_feature: {feature_key: [{id,name}, ...]}
            expanded: optional {feature_key: bool}
            active: optional {feature_key: active_thread_id}
        """
        self.tree.clear()

        expanded = expanded or {}
        active = active or {}
        self._active_threads = dict(active)

        selected_item: Optional[QTreeWidgetItem] = None

        for f in self.features:
            # Keep top-level text empty because we render a custom widget for it.
            # This avoids duplicate text painting (blur/ghosting).
            top = QTreeWidgetItem([""])
            top.setData(0, self.ROLE_KIND, "feature")
            top.setData(0, self.ROLE_FEATURE, f.key)
            top.setFirstColumnSpanned(True)
            top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(top)

            top_widget = QWidget()
            tw_l = QHBoxLayout(top_widget)
            tw_l.setContentsMargins(6, 4, 6, 4)
            tw_l.setSpacing(6)

            lbl = QLabel(f.name)
            lbl.setStyleSheet("background: transparent; color: #111111; font-weight: 600;")
            btn_add = QPushButton("＋")
            btn_add.setObjectName("MiniBtn")
            btn_add.setCursor(Qt.PointingHandCursor)
            btn_add.setToolTip(f"在 {f.name} 下新建对话")
            btn_add.setFixedWidth(30)

            btn_del = QPushButton("－")
            btn_del.setObjectName("MiniBtn")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setToolTip(f"删除 {f.name} 当前对话")
            btn_del.setFixedWidth(30)

            btn_add.clicked.connect(lambda _=False, k=f.key: self._on_add_for_feature(k))
            btn_del.clicked.connect(lambda _=False, k=f.key: self._on_delete_for_feature(k))

            tw_l.addWidget(lbl)
            tw_l.addStretch(1)
            tw_l.addWidget(btn_add)
            tw_l.addWidget(btn_del)
            self.tree.setItemWidget(top, 0, top_widget)

            ths = threads_by_feature.get(f.key, []) or []
            for t in ths:
                tid = str(t.get("id") or "").strip()
                name = str(t.get("name") or tid).strip() or tid
                child = QTreeWidgetItem([name])
                child.setData(0, self.ROLE_KIND, "thread")
                child.setData(0, self.ROLE_FEATURE, f.key)
                child.setData(0, self.ROLE_THREAD, tid)
                top.addChild(child)

                if tid and active.get(f.key) == tid:
                    selected_item = child

            top.setExpanded(bool(expanded.get(f.key, True)))

        self.tree.expandToDepth(0)

        if selected_item is None:
            selected_item = self._first_thread_item()

        if selected_item is not None:
            self.tree.setCurrentItem(selected_item)
            self.tree.scrollToItem(selected_item)

    def current_selection(self) -> Tuple[str, str, str]:
        """Return (feature_key, thread_id, thread_name)."""
        it = self.tree.currentItem()
        if not it:
            return "", "", ""
        kind = it.data(0, self.ROLE_KIND)
        fkey = str(it.data(0, self.ROLE_FEATURE) or "").strip()
        if kind == "thread":
            tid = str(it.data(0, self.ROLE_THREAD) or "").strip()
            return fkey, tid, it.text(0)
        return fkey, "", it.text(0)

    def _first_thread_item(self) -> Optional[QTreeWidgetItem]:
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top and top.childCount() > 0:
                return top.child(0)
        return None

    def _on_current_changed(self, curr: Optional[QTreeWidgetItem], prev: Optional[QTreeWidgetItem]):
        fkey, tid, name = self.current_selection()
        if fkey and tid:
            self._active_threads[fkey] = tid
            self.thread_selected.emit(fkey, tid, name)

    def _resolve_thread_for_feature(self, feature_key: str) -> Tuple[str, str]:
        preferred_tid = str(self._active_threads.get(feature_key) or "").strip()
        first_tid = ""
        first_name = ""

        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if not top:
                continue
            fkey = str(top.data(0, self.ROLE_FEATURE) or "").strip()
            if fkey != feature_key:
                continue

            for j in range(top.childCount()):
                child = top.child(j)
                tid = str(child.data(0, self.ROLE_THREAD) or "").strip()
                name = child.text(0)
                if not first_tid and tid:
                    first_tid, first_name = tid, name
                if preferred_tid and tid == preferred_tid:
                    return tid, name

        return first_tid, first_name

    def _on_add_for_feature(self, feature_key: str):
        fkey = (feature_key or "").strip()
        if not fkey and self.features:
            fkey = self.features[0].key
        if not fkey:
            return

        name, ok = QInputDialog.getText(self, "新建对话", "对话名称：", text="新对话")
        if not ok:
            return
        name = (name or "").strip() or "新对话"

        import uuid
        tid = f"t_{uuid.uuid4().hex[:8]}"
        self.thread_created.emit(fkey, tid, name)

    def _on_delete_for_feature(self, feature_key: str):
        fkey = (feature_key or "").strip()
        tid, name = self._resolve_thread_for_feature(fkey)
        if not (fkey and tid):
            return
        ret = QMessageBox.question(self, "确认删除", f"确定删除对话“{name}”吗？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.thread_deleted.emit(fkey, tid)

    def _filter(self, text: str):
        q = (text or "").strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if not top:
                continue
            any_visible = False
            for j in range(top.childCount()):
                child = top.child(j)
                name = (child.text(0) or "").lower()
                show = (q in name) if q else True
                child.setHidden(not show)
                any_visible = any_visible or show

            if q:
                top.setHidden(not any_visible)
                if any_visible:
                    top.setExpanded(True)
            else:
                top.setHidden(False)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        kind = item.data(0, self.ROLE_KIND)
        if kind != "feature":
            return
        fkey = str(item.data(0, self.ROLE_FEATURE) or "").strip()
        if fkey:
            self.feature_expanded_changed.emit(fkey, True)

    def _on_item_collapsed(self, item: QTreeWidgetItem):
        kind = item.data(0, self.ROLE_KIND)
        if kind != "feature":
            return
        fkey = str(item.data(0, self.ROLE_FEATURE) or "").strip()
        if fkey:
            self.feature_expanded_changed.emit(fkey, False)

