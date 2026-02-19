from __future__ import annotations

"""Submit a fixed prompt to OpenAI when a new sub-chat is created.

Prompt content is placeholder for now.
OpenAI API key / base_url / model are taken from the active profile's OpenAI agent config.
"""

from typing import Any, Dict

from paperscout.services.llm_client import active_profile, agent_cfg, chat_complete, mk_client


INIT_SYSTEM_PROMPT = "You are a helpful assistant."
# TODO: replace with your real fixed prompt
INIT_USER_PROMPT = "Initialize a new arXiv crawling chat session. Reply with a short confirmation."


def submit_init_prompt(settings: Dict[str, Any]) -> str:
    """Call OpenAI chat completion with a fixed prompt.

    Returns assistant content (string). Raises exception on error.
    """
    profile = active_profile(settings)
    cfg = agent_cfg(profile, "openai")

    model = str(cfg.get("model") or "").strip() or "gpt-4o-mini"
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()

    if not api_key:
        raise RuntimeError("OpenAI API Key is empty. Please configure it in Settings → AI 模型配置 → OpenAI.")

    client = mk_client(api_key, base_url)

    return chat_complete(
        client,
        model=model,
        messages=[
            {"role": "system", "content": INIT_SYSTEM_PROMPT},
            {"role": "user", "content": INIT_USER_PROMPT},
        ],
    )
