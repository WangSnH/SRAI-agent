from __future__ import annotations

from typing import Callable, Dict, List

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QWidget


def build_profile_menu(
    parent: QWidget,
    current_profile_id: str,
    profiles: List[Dict],
    on_select: Callable[[str], None],
    on_create: Callable[[], None],
    on_edit: Callable[[str], None],
    on_delete: Callable[[str], None],
) -> QMenu:
    menu = QMenu(parent)

    act_new = QAction("➕ 新建配置集（四模型）...", menu)
    act_new.triggered.connect(on_create)
    menu.addAction(act_new)

    act_edit = QAction("⚙️ 编辑当前配置集（四模型）...", menu)
    act_edit.triggered.connect(lambda: on_edit(current_profile_id))
    menu.addAction(act_edit)

    act_del = QAction("🗑️ 删除当前配置集", menu)
    act_del.setEnabled(len(profiles) > 1)
    act_del.triggered.connect(lambda: on_delete(current_profile_id))
    menu.addAction(act_del)

    menu.addSeparator()

    group = QActionGroup(menu)
    group.setExclusive(True)

    for p in profiles:
        pid = (p.get("id") or "").strip()
        name = (p.get("name") or pid or "未命名配置集").strip()
        act = QAction(name, menu)
        act.setCheckable(True)
        act.setChecked(pid == current_profile_id)
        act.triggered.connect(lambda _=False, k=pid: on_select(k))
        group.addAction(act)
        menu.addAction(act)

    return menu
