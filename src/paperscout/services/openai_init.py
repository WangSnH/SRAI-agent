from __future__ import annotations

"""Submit a fixed prompt to OpenAI when a new sub-chat is created.

Prompt content is placeholder for now.
OpenAI API key / base_url / model are taken from the active profile's OpenAI agent config.
"""

from typing import Any, Dict
from urllib.parse import urlparse

from paperscout.config.settings import find_profile_by_id, get_profile_agent_info


INIT_SYSTEM_PROMPT = "You are a helpful assistant."
# TODO: replace with your real fixed prompt
INIT_USER_PROMPT = "Initialize a new arXiv crawling chat session. Reply with a short confirmation."


def _get_active_profile(settings: Dict[str, Any]) -> Dict[str, Any]:
    llm = settings.get("llm", {}) if isinstance(settings, dict) else {}
    profiles = llm.get("profiles", []) if isinstance(llm, dict) else []
    active_id = str(llm.get("active_profile_id") or "").strip() if isinstance(llm, dict) else ""
    if isinstance(profiles, list) and profiles:
        if active_id:
            p = find_profile_by_id(profiles, active_id)
            if p:
                return p
        return profiles[0] if isinstance(profiles[0], dict) else {}
    return {}


def submit_init_prompt(settings: Dict[str, Any]) -> str:
    """Call OpenAI chat completion with a fixed prompt.

    Returns assistant content (string). Raises exception on error.
    """
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("Python package 'openai' is not installed. Please install openai>=1.0.") from e

    profile = _get_active_profile(settings)
    agent = get_profile_agent_info(profile, "openai")

    model = str(agent.get("model") or "").strip() or "gpt-4o-mini"
    api_key = str(agent.get("api_key") or "").strip()
    base_url = str(agent.get("base_url") or "").strip()
    if base_url:
        p = urlparse(base_url)
        path = (p.path or "").strip()
        if path in ("", "/"):
            base_url = base_url.rstrip("/") + "/v1"

    if not api_key:
        raise RuntimeError("OpenAI API Key is empty. Please configure it in Settings → AI 模型配置 → OpenAI.")

    client = OpenAI(api_key=api_key, base_url=base_url or None)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": INIT_SYSTEM_PROMPT},
            {"role": "user", "content": INIT_USER_PROMPT},
        ],
    )

    try:
        return resp.choices[0].message.content or ""
    except Exception:
        return ""
