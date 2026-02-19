from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RuntimeContextStore:
    """Process-level runtime cache for cross-step transient data."""

    thread_original_inputs: Dict[str, str] = field(default_factory=dict)

    def set_original_input(self, thread_id: str, text: str) -> None:
        tid = str(thread_id or "").strip()
        if not tid:
            return
        self.thread_original_inputs[tid] = str(text or "").strip()

    def get_original_input(self, thread_id: str, default: str = "") -> str:
        tid = str(thread_id or "").strip()
        if not tid:
            return default
        return str(self.thread_original_inputs.get(tid, default) or default)

    def remove_thread(self, thread_id: str) -> None:
        """Remove cached data for a deleted thread."""
        tid = str(thread_id or "").strip()
        if tid:
            self.thread_original_inputs.pop(tid, None)


runtime_store = RuntimeContextStore()
