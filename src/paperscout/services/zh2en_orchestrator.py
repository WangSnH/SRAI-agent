from __future__ import annotations

import re
from typing import Any, Dict, List

from paperscout.config.settings import get_system_param_int
from paperscout.services.llm_client import (
    active_profile,
    agent_cfg,
    chat_complete,
    chat_complete_json,
    mk_client,
)
from paperscout.services.prompts.zh2en_prompts import (
    ZH2EN_CORRECTION_FROM_CACHE_USER_PROMPT_TEMPLATE,
    ZH2EN_CORRECTION_SYSTEM_PROMPT,
    ZH2EN_CHAT_SYSTEM_PROMPT,
    ZH2EN_DEEPSEEK_REFINE_SYSTEM_PROMPT,
    ZH2EN_DEEPSEEK_REFINE_USER_PROMPT_TEMPLATE,
    ZH2EN_INIT_SYSTEM_PROMPT,
    ZH2EN_INIT_USER_PROMPT_TEMPLATE,
    ZH2EN_PERSISTENT_MEMORY_SYSTEM_PROMPT_TEMPLATE,
    ZH2EN_TASK_CLASSIFIER_SYSTEM_PROMPT,
    ZH2EN_TASK_CLASSIFIER_USER_PROMPT_TEMPLATE,
    ZH2EN_TRANSLATION_SYSTEM_PROMPT,
    ZH2EN_TRANSLATION_USER_PROMPT_TEMPLATE,
)


def _openai_agent_from_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    profile = active_profile(settings)
    cfg = agent_cfg(profile, "openai")
    return cfg if isinstance(cfg, dict) else {}


def _deepseek_agent_from_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    profile = active_profile(settings)
    cfg = agent_cfg(profile, "deepseek")
    return cfg if isinstance(cfg, dict) else {}


def _refine_with_deepseek(
    settings: Dict[str, Any],
    user_text: str,
) -> str:
    """Send user_text to DeepSeek for academic refinement before translation.

    Returns the refined text, or the original text on any failure.
    """
    src = str(user_text or "").strip()
    if not src:
        return src

    cfg = _deepseek_agent_from_settings(settings)
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    model = str(cfg.get("model") or "").strip()

    if not api_key or not model:
        return src  # DeepSeek not configured, skip refinement

    try:
        client = mk_client(api_key, base_url)
        refined = chat_complete(
            client,
            model=model,
            messages=[
                {"role": "system", "content": ZH2EN_DEEPSEEK_REFINE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": ZH2EN_DEEPSEEK_REFINE_USER_PROMPT_TEMPLATE.format(user_text=src),
                },
            ],
            temperature=float(cfg.get("temperature", 0.2) or 0.2),
            top_p=float(cfg.get("top_p", 1.0) or 1.0),
            max_tokens=int(cfg.get("max_tokens", 2048) or 2048),
        )
        refined = str(refined or "").strip()
        return refined if refined else src
    except Exception:
        return src


def _normalize_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for msg in history or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip()
        content = str(msg.get("content") or "").strip()
        if role in ("user", "assistant", "system") and content:
            out.append({"role": role, "content": content})
    return out


def _history_as_text(history: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for msg in history:
        raw_role = str(msg.get("role") or "").strip()
        role = "User" if raw_role == "user" else ("Assistant" if raw_role == "assistant" else "System")
        content = str(msg.get("content") or "").strip()
        lines.append(f"[{role}] {content}")
    return "\n".join(lines) if lines else "(empty)"


def _recent_history_for_classifier(history: List[Dict[str, str]], max_items: int = 16) -> List[Dict[str, str]]:
    if max_items <= 0:
        return []
    return list(history[-max_items:])


def _build_persistent_memory(init_meta: Dict[str, Any]) -> str:
    memory_lines: List[str] = []

    original_input = str(init_meta.get("original_input") or "").strip()
    if original_input:
        memory_lines.append(f"- Session original intent: {original_input}")

    init_reply = str(init_meta.get("zh2en_init_reply") or "").strip()
    if init_reply:
        memory_lines.append("- Init strategy:")
        memory_lines.append(init_reply)

    user_memory = str(init_meta.get("zh2en_memory") or "").strip()
    if user_memory:
        memory_lines.append("- User memory preferences:")
        memory_lines.append(user_memory)

    if not memory_lines:
        memory_lines.append("- Default target language: English")
        memory_lines.append("- Keep translation faithful, clear, and terminology-consistent")

    return "\n".join(memory_lines)


def _get_translation_cache_list(init_meta: Dict[str, Any]) -> List[str]:
    values = init_meta.get("zh2en_translation_list") if isinstance(init_meta, dict) else []
    if not isinstance(values, list):
        values = []
    out = [str(x).strip() for x in values if str(x).strip()]

    latest = str((init_meta or {}).get("zh2en_latest_translation") or "").strip()
    if latest and (not out or out[-1] != latest):
        out.append(latest)
    return out


def _extract_revised_translation(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return ""

    patterns = [
        r"Revised Translation\s*[:：]?\s*([\s\S]*?)(?:\n\s*Key Fixes\s*[:：]|$)",
        r"修订后译文\s*[:：]?\s*([\s\S]*?)(?:\n\s*关键修改点\s*[:：]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, src, re.IGNORECASE)
        if m:
            v = str(m.group(1) or "").strip()
            if v:
                return v
    return src


def _classify_task_type(
    settings: Dict[str, Any],
    client: Any,
    model: str,
    history: List[Dict[str, str]],
    user_text: str,
) -> str:
    text = str(user_text or "").strip().lower()
    if text:
        translation_keywords = [
            "翻译", "中译英", "译成英文", "translate", "translation", "to english",
        ]
        revise_keywords = [
            "修改", "润色", "修正", "改写", "优化", "更自然", "更专业", "调整", "改",
            "revise", "polish", "improve", "edit", "fix", "rewrite",
        ]

        has_translate_kw = any(k in text for k in translation_keywords)
        has_revise_kw = any(k in text for k in revise_keywords)
        has_translation_object = any(k in text for k in ["译文", "translation", "previous translation", "刚才", "上一版"])

        if has_translation_object and has_revise_kw:
            return "other"

        if has_revise_kw and not has_translate_kw:
            return "other"
        if has_translate_kw and not has_revise_kw:
            return "translation"

    schema = {
        "type": "object",
        "properties": {
            "task_type": {
                "type": "string",
                "enum": ["translation", "other"],
            },
            "reason": {"type": "string"},
        },
        "required": ["task_type", "reason"],
        "additionalProperties": False,
    }

    parsed = chat_complete_json(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": ZH2EN_TASK_CLASSIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ZH2EN_TASK_CLASSIFIER_USER_PROMPT_TEMPLATE.format(
                    history_text=_history_as_text(
                        _recent_history_for_classifier(
                            history,
                            max_items=16,
                        )
                    ),
                    user_text=(user_text or "").strip(),
                ),
            },
        ],
        schema_name="zh2en_task_classifier",
        schema=schema,
        timeout_sec=15.0,
    )

    candidate = str(parsed.get("task_type") or "").strip().lower()
    return candidate if candidate in ("translation", "other") else "translation"


def run_zh2en_init(settings: Dict[str, Any], thread_name: str, original_input: str) -> Dict[str, Any]:
    cfg = _openai_agent_from_settings(settings)
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    model = str(cfg.get("model") or "").strip()

    if not model:
        raise RuntimeError("OpenAI model 为空（请在设置里选择模型）")
    if not api_key:
        raise RuntimeError("OpenAI API Key 为空（请在设置里配置）")

    client = mk_client(api_key, base_url)
    prompt = ZH2EN_INIT_USER_PROMPT_TEMPLATE.format(
        thread_name=(thread_name or "新对话"),
        original_input=(original_input or thread_name or "").strip(),
    )
    reply = chat_complete(
        client,
        model=model,
        messages=[
            {"role": "system", "content": ZH2EN_INIT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=float(cfg.get("temperature", 0.2) or 0.2),
        top_p=float(cfg.get("top_p", 1.0) or 1.0),
        max_tokens=int(cfg.get("max_tokens", 1024) or 1024),
    )

    return {
        "zh2en_init_reply": reply,
        "used_model": model,
        "zh2en_translation_list": [],
        "zh2en_latest_translation": "",
    }


def run_zh2en_turn(
    settings: Dict[str, Any],
    history: List[Dict[str, str]],
    user_text: str,
    init_meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = _openai_agent_from_settings(settings)
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    model = str(cfg.get("model") or "").strip()

    if not model:
        raise RuntimeError("OpenAI model 为空（请在设置里选择模型）")
    if not api_key:
        raise RuntimeError("OpenAI API Key 为空（请在设置里配置）")

    init_meta = init_meta or {}
    translation_list = _get_translation_cache_list(init_meta)

    client = mk_client(api_key, base_url)
    normalized_history = _normalize_history(history)
    persistent_memory = _build_persistent_memory(init_meta)

    task_type = _classify_task_type(
        settings=settings,
        client=client,
        model=model,
        history=normalized_history,
        user_text=user_text,
    )

    # ── DeepSeek 预处理：仅对 translation 分支做中文学术润色 ──
    # "other" (correction) 分支的输入是修改指令而非待翻译文本，不应润色
    refined_text = _refine_with_deepseek(settings, user_text) if task_type == "translation" else user_text

    messages: List[Dict[str, str]] = [{"role": "system", "content": ZH2EN_CHAT_SYSTEM_PROMPT}]
    messages.append(
        {
            "role": "system",
            "content": ZH2EN_PERSISTENT_MEMORY_SYSTEM_PROMPT_TEMPLATE.format(memory_block=persistent_memory),
        }
    )

    init_reply = str(init_meta.get("zh2en_init_reply") or "").strip()
    if init_reply:
        messages.append({"role": "system", "content": f"（初始化翻译策略）\n{init_reply}"})

    if task_type == "other":
        messages.append({"role": "system", "content": ZH2EN_CORRECTION_SYSTEM_PROMPT})
    else:
        messages.append({"role": "system", "content": ZH2EN_TRANSLATION_SYSTEM_PROMPT})

    # 保留并注入完整对话记忆（不做截断）
    messages.extend(normalized_history)

    final_answer = ""
    latest_translation_for_cache = ""
    if task_type == "other":
        latest_translation = translation_list[-1] if translation_list else ""
        if not latest_translation:
            return {
                "final_answer": "当前还没有可修改的译文。请先发送一段需要翻译的内容。",
                "task_type": task_type,
                "updated_init_meta": dict(init_meta),
            }
        workflow_user_prompt = ZH2EN_CORRECTION_FROM_CACHE_USER_PROMPT_TEMPLATE.format(
            latest_translation=latest_translation,
            user_requirement=(refined_text or "").strip(),
        )
    else:
        workflow_user_prompt = ZH2EN_TRANSLATION_USER_PROMPT_TEMPLATE.format(user_text=(refined_text or "").strip())
    messages.append({"role": "user", "content": workflow_user_prompt})

    final_answer = chat_complete(
        client,
        model=model,
        messages=messages,
        temperature=float(cfg.get("temperature", 0.2) or 0.2),
        top_p=float(cfg.get("top_p", 1.0) or 1.0),
        max_tokens=int(cfg.get("max_tokens", 2048) or 2048),
    )

    if task_type == "translation":
        latest_translation_for_cache = str(final_answer or "").strip()
    else:
        latest_translation_for_cache = _extract_revised_translation(final_answer)

    if latest_translation_for_cache:
        translation_list.append(latest_translation_for_cache)
        cache_size = get_system_param_int(settings, "zh2en_translation_cache_size", 3, 1, 20)
        translation_list = translation_list[-cache_size:]

    updated_init_meta = dict(init_meta)
    updated_init_meta["zh2en_translation_list"] = translation_list
    updated_init_meta["zh2en_latest_translation"] = translation_list[-1] if translation_list else ""

    return {
        "final_answer": final_answer,
        "task_type": task_type,
        "updated_init_meta": updated_init_meta,
    }
