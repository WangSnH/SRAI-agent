from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from paperscout.config.ui_state import remove_legacy_default_threads


def test_remove_legacy_default_threads_removes_placeholder_and_repairs_active():
    settings = {
        "ui": {
            "features": {
                "arxiv": {
                    "threads": [
                        {"id": "t_default", "name": "默认对话"},
                        {"id": "t_real", "name": "真实会话"},
                    ],
                    "active_thread_id": "t_default",
                }
            }
        }
    }

    changed = remove_legacy_default_threads(settings)

    assert changed is True
    arxiv = settings["ui"]["features"]["arxiv"]
    assert arxiv["threads"] == [{"id": "t_real", "name": "真实会话"}]
    assert arxiv["active_thread_id"] == "t_real"


def test_remove_legacy_default_threads_keeps_non_placeholder_threads():
    settings = {
        "ui": {
            "features": {
                "zh2en": {
                    "threads": [
                        {"id": "t1", "name": "翻译会话A"},
                        {"id": "t2", "name": "翻译会话B"},
                    ],
                    "active_thread_id": "t2",
                }
            }
        }
    }

    changed = remove_legacy_default_threads(settings)

    assert changed is False
    zh2en = settings["ui"]["features"]["zh2en"]
    assert zh2en["threads"] == [
        {"id": "t1", "name": "翻译会话A"},
        {"id": "t2", "name": "翻译会话B"},
    ]
    assert zh2en["active_thread_id"] == "t2"


def test_remove_legacy_default_threads_clears_active_when_all_removed():
    settings = {
        "ui": {
            "features": {
                "arxiv": {
                    "threads": [{"id": "t_default", "name": "默认对话"}],
                    "active_thread_id": "t_default",
                }
            }
        }
    }

    changed = remove_legacy_default_threads(settings)

    assert changed is True
    arxiv = settings["ui"]["features"]["arxiv"]
    assert arxiv["threads"] == []
    assert arxiv["active_thread_id"] == ""


def test_remove_legacy_default_threads_repairs_active_with_dirty_thread_list():
    settings = {
        "ui": {
            "features": {
                "arxiv": {
                    "threads": [
                        "bad-item",
                        {"id": "t_default", "name": "默认对话"},
                        {"id": "t_ok", "name": "保留会话"},
                    ],
                    "active_thread_id": "t_default",
                }
            }
        }
    }

    changed = remove_legacy_default_threads(settings)

    assert changed is True
    arxiv = settings["ui"]["features"]["arxiv"]
    assert arxiv["threads"] == ["bad-item", {"id": "t_ok", "name": "保留会话"}]
    assert arxiv["active_thread_id"] == "t_ok"
