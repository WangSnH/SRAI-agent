from __future__ import annotations

"""Shared LLM client utilities.

Consolidates common functions previously duplicated across
zh2en_orchestrator, dual_orchestrator, and openai_init.
"""

import json
import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

from paperscout.config.settings import find_profile_by_id, get_profile_agent_info

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


def active_profile(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the currently active LLM profile from settings."""
    llm = settings.get("llm", {}) if isinstance(settings, dict) else {}
    profiles = llm.get("profiles", []) if isinstance(llm, dict) else []
    active_id = str(llm.get("active_profile_id") or "").strip() if isinstance(llm, dict) else ""
    if isinstance(profiles, list) and profiles:
        if active_id:
            p = find_profile_by_id(profiles, active_id)
            if isinstance(p, dict) and p:
                return p
        return profiles[0] if isinstance(profiles[0], dict) else {}
    return {}


def agent_cfg(profile: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """Return agent config with API key resolved from keyring if configured."""
    try:
        cfg = get_profile_agent_info(profile, provider)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        agents = profile.get("agents", {}) if isinstance(profile, dict) else {}
        if not isinstance(agents, dict):
            return {}
        raw = agents.get(provider, {})
        return raw if isinstance(raw, dict) else {}


def normalize_base_url(base_url: str) -> str:
    """Normalize a base URL: append /v1 only when path is empty."""
    normalized = str(base_url or "").strip()
    if normalized:
        p = urlparse(normalized)
        path = (p.path or "").strip()
        if path in ("", "/"):
            normalized = normalized.rstrip("/") + "/v1"
    return normalized


def mk_client(api_key: str, base_url: str, timeout: float = 30.0) -> Any:
    """Create an OpenAI-compatible client."""
    if OpenAI is None:
        raise RuntimeError("缺少依赖 openai，请先安装：pip install openai>=1.0")
    normalized = normalize_base_url(base_url)
    return OpenAI(api_key=api_key, base_url=(normalized or None), timeout=timeout, max_retries=1)


def chat_complete(
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    top_p: float = 1.0,
    max_tokens: int = 2048,
    timeout_sec: float = 30.0,
) -> str:
    """Run a chat completion and return the assistant content string."""
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        timeout=timeout_sec,
    )
    try:
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


def chat_complete_json(
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
    schema_name: str,
    schema: Dict[str, Any],
    timeout_sec: float = 20.0,
) -> Dict[str, Any]:
    """Run a chat completion requesting JSON output.

    Tries ``json_schema`` structured output first (requires gpt-4o+).
    Falls back to ``{"type": "json_object"}`` if the model does not
    support ``json_schema``, and finally attempts plain-text extraction
    as a last resort.
    """
    # --- Attempt 1: json_schema (structured output) ---
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            top_p=1.0,
            max_tokens=256,
            timeout=timeout_sec,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )
        text = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        logger.debug(f"json_schema attempt failed ({e}), falling back to json_object")

    # --- Attempt 2: json_object (broader compatibility) ---
    try:
        # Add explicit instruction for JSON output
        patched = list(messages)
        if patched and patched[0].get("role") == "system":
            patched[0] = dict(patched[0])
            patched[0]["content"] = patched[0]["content"] + "\n\nReturn your answer as a JSON object."
        resp = client.chat.completions.create(
            model=model,
            messages=patched,
            temperature=0.0,
            top_p=1.0,
            max_tokens=256,
            timeout=timeout_sec,
            response_format={"type": "json_object"},
        )
        text = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        logger.debug(f"json_object attempt failed ({e}), falling back to plain text")

    # --- Attempt 3: plain text extraction ---
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            top_p=1.0,
            max_tokens=256,
            timeout=timeout_sec,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Try to find a JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass

    return {}
