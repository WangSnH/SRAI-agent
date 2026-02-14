from __future__ import annotations

import re
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

    def upsert_system_line(self, text: str, session_id: Optional[str] = None, key: str = "progress_line_idx"):
        sid = (session_id or self._current_session).strip() or "default"
        self._sessions.setdefault(sid, [])
        self._meta.setdefault(sid, {})

        idx = self._meta[sid].get(key)
        if isinstance(idx, int) and 0 <= idx < len(self._sessions[sid]):
            msg = self._sessions[sid][idx]
            if msg.role == "system":
                msg.text = text
                return

        self._sessions[sid].append(ChatMessage(role="system", text=text, ts=datetime.now()))
        self._meta[sid][key] = len(self._sessions[sid]) - 1

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

        def linkify_text(s: str) -> str:
            text = esc(s)

            md_pat = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
            placeholders: List[str] = []

            def md_repl(match: re.Match) -> str:
                label = match.group(1)
                url = match.group(2)
                idx = len(placeholders)
                placeholders.append(
                    f'<a href="{url}" style="color:#1677ff; text-decoration:underline;">{label}</a>'
                )
                return f"§§LINK{idx}§§"

            text = md_pat.sub(md_repl, text)

            url_pat = re.compile(r"(?<![\"'=])(https?://[^\s<]+)")

            def url_repl(match: re.Match) -> str:
                url = match.group(1)
                tail = ""
                while url and url[-1] in ".,;:!?)":
                    tail = url[-1] + tail
                    url = url[:-1]
                if not url:
                    return match.group(1)
                return f'<a href="{url}" style="color:#1677ff; text-decoration:underline;">{url}</a>{tail}'

            text = url_pat.sub(url_repl, text)

            for idx, html in enumerate(placeholders):
                text = text.replace(f"§§LINK{idx}§§", html)

            return text

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
                                            <div style="white-space:pre-wrap;">{linkify_text(m.text)}</div>
                    </div>
                  </div>
                """
                )
            else:
                parts.append(
                    f"""
                  <div style="margin:10px 0; text-align:center; color:#888; font-size:12px;">
                                        {t} · {linkify_text(m.text)}
                  </div>
                """
                )

        parts.append("</div>")
        return "".join(parts)
