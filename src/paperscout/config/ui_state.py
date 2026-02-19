from __future__ import annotations

"""UI state persisted inside the same settings file.

We keep UI-only data (e.g., conversation list) under `settings["ui"]`.
This avoids changing the LLM schema and stays backward compatible.
"""

from typing import Any, Dict, List, Tuple
from uuid import uuid4


DEFAULT_FEATURES = {
    "arxiv": {"name": "爬取arxiv"},
    "zh2en": {"name": "中译英"},
}

LEGACY_DEFAULT_THREAD_NAMES = {"默认对话"}


def _new_thread_id() -> str:
    return f"t_{uuid4().hex[:8]}"


def ensure_ui_state(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure `settings['ui']` exists and has required defaults."""
    if not isinstance(settings, dict):
        return {"ui": {}}

    ui = settings.setdefault("ui", {})
    if not isinstance(ui, dict):
        ui = {}
        settings["ui"] = ui

    # 初始化超时（秒），默认 300 秒（5 分钟）
    timeout_sec = ui.get("init_timeout_sec", 300)
    try:
        timeout_sec = int(timeout_sec)
    except Exception:
        timeout_sec = 300
    timeout_sec = max(60, min(1800, timeout_sec))
    ui["init_timeout_sec"] = timeout_sec

    features = ui.setdefault("features", {})
    if not isinstance(features, dict):
        features = {}
        ui["features"] = features

    for fkey, fdef in DEFAULT_FEATURES.items():
        f = features.setdefault(fkey, {})
        if not isinstance(f, dict):
            f = {}
            features[fkey] = f

        f.setdefault("name", fdef.get("name", fkey))
        f.setdefault("expanded", True)

        threads = f.setdefault("threads", [])
        if not isinstance(threads, list):
            threads = []
            f["threads"] = threads

        active = str(f.get("active_thread_id") or "").strip()
        if threads and (not active or active not in {str(x.get("id") or "").strip() for x in threads}):
            f["active_thread_id"] = str(threads[0].get("id") or "").strip()

    return settings


def remove_legacy_default_threads(settings: Dict[str, Any]) -> bool:
    """Remove legacy placeholder threads like '默认对话' from persisted UI state.

    Returns:
        True when settings are modified, otherwise False.
    """
    if not isinstance(settings, dict):
        return False

    ui = settings.get("ui", {})
    if not isinstance(ui, dict):
        return False

    features = ui.get("features", {})
    if not isinstance(features, dict):
        return False

    changed = False

    for f in features.values():
        if not isinstance(f, dict):
            continue

        threads = f.get("threads", [])
        if not isinstance(threads, list):
            continue

        active_id = str(f.get("active_thread_id") or "").strip()
        kept_threads = []
        removed_any = False

        for t in threads:
            if not isinstance(t, dict):
                kept_threads.append(t)
                continue
            name = str(t.get("name") or "").strip()
            if name in LEGACY_DEFAULT_THREAD_NAMES:
                removed_any = True
                continue
            kept_threads.append(t)

        if removed_any:
            f["threads"] = kept_threads
            changed = True

        valid_ids = {
            str(t.get("id") or "").strip()
            for t in kept_threads
            if isinstance(t, dict)
        }
        first_valid_id = ""
        for t in kept_threads:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id") or "").strip()
            if tid:
                first_valid_id = tid
                break

        if not valid_ids:
            new_active = ""
        elif not active_id or active_id not in valid_ids:
            new_active = first_valid_id
        else:
            new_active = active_id

        if new_active != active_id:
            f["active_thread_id"] = new_active
            changed = True

    return changed


def list_threads(settings: Dict[str, Any], feature_key: str) -> List[Dict[str, str]]:
    ui = settings.get("ui", {}) if isinstance(settings, dict) else {}
    features = ui.get("features", {}) if isinstance(ui, dict) else {}
    f = features.get(feature_key, {}) if isinstance(features, dict) else {}
    threads = f.get("threads", []) if isinstance(f, dict) else []
    if not isinstance(threads, list):
        return []
    out: List[Dict[str, str]] = []
    for t in threads:
        if isinstance(t, dict):
            tid = str(t.get("id") or "").strip()
            name = str(t.get("name") or "").strip()
            if tid:
                out.append({"id": tid, "name": name or tid})
    return out


def active_thread(settings: Dict[str, Any], feature_key: str) -> Tuple[str, str]:
    threads = list_threads(settings, feature_key)
    ui = settings.get("ui", {}) if isinstance(settings, dict) else {}
    features = ui.get("features", {}) if isinstance(ui, dict) else {}
    f = features.get(feature_key, {}) if isinstance(features, dict) else {}
    active_id = str(f.get("active_thread_id") or "").strip() if isinstance(f, dict) else ""

    for t in threads:
        if t["id"] == active_id:
            return t["id"], t["name"]
    if threads:
        return threads[0]["id"], threads[0]["name"]
    return "", ""


def set_active_thread(settings: Dict[str, Any], feature_key: str, thread_id: str) -> None:
    ui = settings.setdefault("ui", {})
    features = ui.setdefault("features", {})
    f = features.setdefault(feature_key, {})
    if isinstance(f, dict):
        f["active_thread_id"] = str(thread_id or "").strip()


def add_thread(settings: Dict[str, Any], feature_key: str, thread_id: str, thread_name: str) -> None:
    ui = settings.setdefault("ui", {})
    features = ui.setdefault("features", {})
    f = features.setdefault(feature_key, {})
    if not isinstance(f, dict):
        f = {}
        features[feature_key] = f

    threads = f.setdefault("threads", [])
    if not isinstance(threads, list):
        threads = []
        f["threads"] = threads

    tid = str(thread_id or "").strip()
    if not tid:
        return

    existing = {
        str(t.get("id") or "").strip()
        for t in threads
        if isinstance(t, dict)
    }
    if tid not in existing:
        threads.append({"id": tid, "name": (thread_name or tid).strip() or tid})

    f["active_thread_id"] = tid
