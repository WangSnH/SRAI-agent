from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QHBoxLayout


@dataclass
class TaskItem:
    key: str
    name: str
    meta: str


class _TaskItemWidget(QWidget):
    def __init__(self, name: str, meta: str):
        super().__init__()
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        avatar = QLabel(name[:1])
        avatar.setObjectName("Avatar")
        avatar.setFixedSize(32, 32)

        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)

        lbl_name = QLabel(name)
        lbl_name.setObjectName("TaskName")
        lbl_meta = QLabel(meta)
        lbl_meta.setObjectName("TaskMeta")

        box.addWidget(lbl_name)
        box.addWidget(lbl_meta)

        root.addWidget(avatar)
        root.addLayout(box, 1)


class TaskSidebar(QWidget):
    task_changed = Signal(str, str)  # (task_key, task_name)

    def __init__(self, tasks: List[TaskItem], parent=None):
        super().__init__(parent)

        self.tasks = tasks

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("任务 / Tasks")
        title.setObjectName("LeftTitle")

        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("搜索任务…")
        self.search.setClearButtonEnabled(True)

        self.list = QListWidget()
        self.list.setObjectName("TaskList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        layout.addWidget(title)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)

        self._load()
        self.list.setCurrentRow(0)

        self.search.textChanged.connect(self._filter)
        self.list.currentItemChanged.connect(self._emit_changed)

    def _load(self):
        self.list.clear()
        for t in self.tasks:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, t.key)
            it.setData(Qt.UserRole + 1, t.name)
            it.setData(Qt.UserRole + 2, t.meta)
            it.setSizeHint(QSize(260, 62))
            self.list.addItem(it)
            self.list.setItemWidget(it, _TaskItemWidget(t.name, t.meta))

    def current_task(self) -> tuple[str, str]:
        it = self.list.currentItem()
        if not it:
            return "", "（未选择任务）"
        return it.data(Qt.UserRole) or "", it.data(Qt.UserRole + 1) or "（未选择任务）"

    def _emit_changed(self, curr: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        key, name = self.current_task()
        if name:
            self.task_changed.emit(key, name)

    def _filter(self, text: str):
        text = (text or "").strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            name = (it.data(Qt.UserRole + 1) or "").lower()
            meta = (it.data(Qt.UserRole + 2) or "").lower()
            it.setHidden(text not in name and text not in meta)
