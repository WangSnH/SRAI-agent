from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ChatMessage:
    role: str   # "user" / "assistant" / "system"
    text: str
    ts: datetime


class ChatController:
    """In-memory multi-session chat store + per-session meta."""
    def __init__(self):
        self._sessions: Dict[str, List[ChatMessage]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._current_session: str = "default"

    def set_session(self, session_id: str):
        session_id = (session_id or "").strip() or "default"
        self._current_session = session_id
        self._sessions.setdefault(session_id, [])
        self._meta.setdefault(session_id, {})

    def current_session_id(self) -> str:
        return self._current_session

    def add(self, role: str, text: str, session_id: Optional[str] = None):
        sid = (session_id or self._current_session).strip() or "default"
        self._sessions.setdefault(sid, []).append(ChatMessage(role=role, text=text, ts=datetime.now()))

    def messages(self, session_id: Optional[str] = None) -> List[ChatMessage]:
        sid = (session_id or self._current_session).strip() or "default"
        return self._sessions.setdefault(sid, [])

    def set_meta(self, key: str, value: Any, session_id: Optional[str] = None):
        sid = (session_id or self._current_session).strip() or "default"
        self._meta.setdefault(sid, {})[key] = value

    def get_meta(self, key: str, default: Any = None, session_id: Optional[str] = None) -> Any:
        sid = (session_id or self._current_session).strip() or "default"
        return self._meta.setdefault(sid, {}).get(key, default)

    def render_html(self, context_name: str, model_name: str, session_id: Optional[str] = None) -> str:
        def esc(s: str) -> str:
            return (
                s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
            )

        msgs = self.messages(session_id)

        parts = ['<div style="padding:12px 14px; font-family: sans-serif;">']
        parts.append(
            f'<div style="color:#666; margin-bottom:8px;">'
            f'对话：<b>{esc(context_name)}</b> · 配置：<b>{esc(model_name)}</b>'
            f"</div>"
        )

        for m in msgs[-200:]:
            t = m.ts.strftime("%H:%M")
            if m.role == "user":
                parts.append(
                    f"""
                  <div style="margin:10px 0; display:flex; justify-content:flex-end;">
                    <div style="max-width:70%; background:#1677ff; color:white; padding:10px 12px; border-radius:14px;">
                      <div style="font-size:12px; opacity:0.9; margin-bottom:4px;">你 · {t}</div>
                      <div style="white-space:pre-wrap;">{esc(m.text)}</div>
                    </div>
                  </div>
                """
                )
            elif m.role == "assistant":
                parts.append(
                    f"""
                  <div style="margin:10px 0; display:flex; justify-content:flex-start;">
                    <div style="max-width:70%; background:#f2f4f7; color:#111; padding:10px 12px; border-radius:14px;">
                      <div style="font-size:12px; color:#666; margin-bottom:4px;">助手 · {t}</div>
                      <div style="white-space:pre-wrap;">{esc(m.text)}</div>
                    </div>
                  </div>
                """
                )
            else:
                parts.append(
                    f"""
                  <div style="margin:10px 0; text-align:center; color:#888; font-size:12px;">
                    {t} · {esc(m.text)}
                  </div>
                """
                )

        parts.append("</div>")
        return "".join(parts)
