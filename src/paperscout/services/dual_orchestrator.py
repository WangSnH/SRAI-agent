from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from paperscout.config.settings import get_profile_agent_info, get_system_param_float, get_system_param_int
from paperscout.services.prompts.arxiv_prompts import (
    OPENAI_ARXIV_API_PROMPT_TEMPLATE,
    OPENAI_ARXIV_API_SYSTEM_PROMPT,
    OPENAI_ARXIV_COMPARE_PROMPT_TEMPLATE,
    OPENAI_ARXIV_COMPARE_SYSTEM_PROMPT,
    OPENAI_ARXIV_ORGANIZE_PROMPT_TEMPLATE,
    OPENAI_ARXIV_ORGANIZE_SYSTEM_PROMPT,
)


try:
    from openai import OpenAI
except Exception as e:
    OpenAI = None  # type: ignore


# ====== 占位：初始化 prompt（你后续再替换）======
OPENAI_INIT_PROMPT = "（占位）你是 PaperScout 的主模型 OpenAI。请初始化本对话。"

# ====== 占位：系统提示（你后续再替换）======
OPENAI_SYSTEM_PROMPT = (
    "你是 PaperScout 的聊天助手（OpenAI）。"
    "请基于用户输入与历史对话给出清晰、可执行的回答。"
)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _active_profile(settings: Dict[str, Any]) -> Dict[str, Any]:
    llm = settings.get("llm", {}) if isinstance(settings, dict) else {}
    profiles = llm.get("profiles", []) if isinstance(llm, dict) else []
    active_id = str(llm.get("active_profile_id") or "").strip() if isinstance(llm, dict) else ""
    if isinstance(profiles, list) and profiles:
        if active_id:
            for p in profiles:
                if isinstance(p, dict) and str(p.get("id") or "").strip() == active_id:
                    return p
        return profiles[0] if isinstance(profiles[0], dict) else {}
    return {}


def _agent_cfg(profile: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """Return agent config with API key resolved from keyring if configured."""
    try:
        cfg = get_profile_agent_info(profile, provider)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        # fallback to raw dict (best effort)
        agents = profile.get("agents", {}) if isinstance(profile, dict) else {}
        if not isinstance(agents, dict):
            return {}
        raw = agents.get(provider, {})
        return raw if isinstance(raw, dict) else {}



def _mk_client(api_key: str, base_url: str) -> Any:
    if OpenAI is None:
        raise RuntimeError("缺少依赖 openai，请先安装：pip install openai>=1.0")
    normalized = str(base_url or "").strip()
    if normalized:
        p = urlparse(normalized)
        path = (p.path or "").strip()
        if path in ("", "/"):
            normalized = normalized.rstrip("/") + "/v1"
    return OpenAI(api_key=api_key, base_url=(normalized or None), timeout=30.0, max_retries=1)


def _chat_complete(
    client: Any,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    top_p: float = 1.0,
    max_tokens: int = 2048,
    timeout_sec: float = 30.0,
) -> str:
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


def translate_input_for_retrieval(settings: Dict[str, Any], text: str) -> str:
    """Translate Chinese user input into concise English retrieval query.

    This is best-effort and will always fall back to the original input on failure.
    """
    src = str(text or "").strip()
    if not src:
        return ""
    if not _contains_cjk(src):
        return src

    try:
        profile = _active_profile(settings)
        openai_cfg = _agent_cfg(profile, "openai")
        api_key = str(openai_cfg.get("api_key") or "").strip()
        base_url = str(openai_cfg.get("base_url") or "").strip()
        model = str(openai_cfg.get("model") or "").strip()
        if not api_key or not model:
            return src

        client = _mk_client(api_key, base_url)
        translated = _chat_complete(
            client,
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a translation assistant for academic retrieval. "
                        "Translate Chinese input into concise, precise English query text for searching papers. "
                        "Return plain English only, no markdown, no explanation."
                    ),
                },
                {"role": "user", "content": src},
            ],
            temperature=0.0,
            top_p=1.0,
            max_tokens=220,
            timeout_sec=20.0,
        )
        translated = str(translated or "").strip()
        return translated or src
    except Exception:
        return src


def _extract_first_json_object(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""

    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", s, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start:end + 1].strip()
    return ""


def _normalize_arxiv_payload(payload: Dict[str, Any], default_max_results: int = 20) -> Dict[str, Any]:
    raw_arxiv = payload.get("arxiv") if isinstance(payload, dict) else {}
    arxiv = raw_arxiv if isinstance(raw_arxiv, dict) else {}

    categories = arxiv.get("categories")
    keywords = arxiv.get("keywords")
    max_results = arxiv.get("max_results", default_max_results)

    if not isinstance(categories, list):
        categories = ["cs.AI", "cs.LG"]
    if not isinstance(keywords, list):
        keywords = ["large language model", "transformer"]

    categories = [str(x).strip() for x in categories if str(x).strip()]
    keywords = [str(x).strip() for x in keywords if str(x).strip()]
    categories = categories[:2]
    keywords = keywords[:2]
    if not categories:
        categories = ["cs.AI", "cs.LG"]
    if not keywords:
        keywords = ["large language model", "transformer"]

    try:
        max_results_i = int(max_results)
    except Exception:
        max_results_i = int(default_max_results)
    max_results_i = max(1, min(300, max_results_i))

    return {
        "arxiv": {
            "categories": categories,
            "keywords": keywords,
            "max_results": max_results_i,
        }
    }


def generate_arxiv_api_payload(
    settings: Dict[str, Any],
    feature_key: str,
    thread_name: str,
    original_input: str = "",
) -> Dict[str, Any]:
    """Use the first OpenAI init prompt to generate structured arXiv API payload."""
    profile = _active_profile(settings)
    openai_cfg = _agent_cfg(profile, "openai")

    api_key = str(openai_cfg.get("api_key") or "").strip()
    base_url = str(openai_cfg.get("base_url") or "").strip()
    model = str(openai_cfg.get("model") or "").strip()
    if not model:
        raise RuntimeError("OpenAI model 为空（请在设置里选择模型）")
    if not api_key:
        raise RuntimeError("OpenAI API Key 为空（请在设置里配置）")

    default_max_results = get_system_param_int(settings, "arxiv_api_default_max_results", 40, 5, 300)

    client = _mk_client(api_key, base_url)
    try:
        prompt = OPENAI_ARXIV_API_PROMPT_TEMPLATE.format(
            feature_key=feature_key or "arxiv",
            thread_name=thread_name or "新对话",
            original_input=(original_input or thread_name or "").strip(),
            default_max_results=default_max_results,
        )
    except Exception as e:
        raise RuntimeError(f"arXiv 参数 Prompt 模板格式化失败：{e}") from e

    raw = _chat_complete(
        client,
        model=model,
        messages=[
            {"role": "system", "content": OPENAI_ARXIV_API_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        top_p=1.0,
        max_tokens=800,
    )

    if not raw:
        return _normalize_arxiv_payload({}, default_max_results=default_max_results)

    json_text = _extract_first_json_object(raw)
    if not json_text:
        return _normalize_arxiv_payload({}, default_max_results=default_max_results)

    try:
        parsed = json.loads(json_text)
    except Exception:
        return _normalize_arxiv_payload({}, default_max_results=default_max_results)

    return _normalize_arxiv_payload(
        parsed if isinstance(parsed, dict) else {},
        default_max_results=default_max_results,
    )

def _compare_weights(settings: Dict[str, Any]) -> Dict[str, float]:
    wr = get_system_param_float(settings, "weight_relevance", 0.55, 0.0, 1_000_000.0)
    wn = get_system_param_float(settings, "weight_novelty", 0.30, 0.0, 1_000_000.0)
    wre = get_system_param_float(settings, "weight_recency", 0.10, 0.0, 1_000_000.0)
    wc = get_system_param_float(settings, "weight_citation", 0.05, 0.0, 1_000_000.0)

    total = wr + wn + wre + wc
    if total <= 1e-9:
        return {
            "relevance": 0.55,
            "novelty": 0.30,
            "recency": 0.10,
            "citation": 0.05,
        }

    return {
        "relevance": wr / total,
        "novelty": wn / total,
        "recency": wre / total,
        "citation": wc / total,
    }


def _normalize_compare_payload(payload: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    summary = str(payload.get("summary") or "").strip()
    top_matches = payload.get("top_matches")

    normalized_matches: List[Dict[str, Any]] = []
    if isinstance(top_matches, list):
        for item in top_matches:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            reason = str(item.get("reason") or "").strip()

            details = item.get("score_details")
            details = details if isinstance(details, dict) else {}

            def _d(name: str, dets: dict = details) -> float:
                try:
                    v = float(dets.get(name, 0.0))
                except Exception:
                    v = 0.0
                return max(0.0, min(1.0, v))

            if pid or title:
                details_payload = {
                    "relevance": round(_d("relevance"), 4),
                    "recency": round(_d("recency"), 4),
                    "novelty": round(_d("novelty"), 4),
                    "citation": round(_d("citation"), 4),
                }
                weighted_score = (
                    details_payload["relevance"] * float(weights.get("relevance", 0.55))
                    + details_payload["novelty"] * float(weights.get("novelty", 0.30))
                    + details_payload["recency"] * float(weights.get("recency", 0.10))
                    + details_payload["citation"] * float(weights.get("citation", 0.05))
                )
                normalized_matches.append(
                    {
                        "id": pid,
                        "title": title,
                        "reason": reason,
                        "score": round(weighted_score, 4),
                        "score_details": details_payload,
                    }
                )

    def _priority_key(item: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
        details = item.get("score_details") if isinstance(item.get("score_details"), dict) else {}
        relevance = float(details.get("relevance", 0.0) or 0.0)
        novelty = float(details.get("novelty", 0.0) or 0.0)
        recency = float(details.get("recency", 0.0) or 0.0)
        citation = float(details.get("citation", 0.0) or 0.0)
        score = float(item.get("score", 0.0) or 0.0)
        return (score, relevance, novelty, recency, citation)

    normalized_matches.sort(key=_priority_key, reverse=True)
    normalized_matches = normalized_matches[:5]
    selected_ids = [str(x.get("id") or "").strip() for x in normalized_matches if str(x.get("id") or "").strip()]

    return {
        "summary": summary,
        "selected_ids": selected_ids,
        "top_matches": normalized_matches,
    }


def compare_arxiv_abstracts_with_input(
    settings: Dict[str, Any],
    original_input: str,
    papers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Second OpenAI prompt: compare fetched paper abstracts against original input."""
    if not papers:
        return {
            "summary": "无候选论文可比较。",
            "selected_ids": [],
            "top_matches": [],
            "used_model": "",
            "compare_limit": 0,
        }

    profile = _active_profile(settings)
    openai_cfg = _agent_cfg(profile, "openai")
    weights = _compare_weights(settings)

    api_key = str(openai_cfg.get("api_key") or "").strip()
    base_url = str(openai_cfg.get("base_url") or "").strip()
    model = str(openai_cfg.get("model") or "").strip()
    if not model:
        raise RuntimeError("OpenAI model 为空（请在设置里选择模型）")
    if not api_key:
        raise RuntimeError("OpenAI API Key 为空（请在设置里配置）")

    compact_papers: List[Dict[str, Any]] = []
    compare_limit = get_system_param_int(settings, "second_prompt_truncate_count", 80, 5, 200)
    for p in papers[:compare_limit]:
        if not isinstance(p, dict):
            continue
        compact_papers.append(
            {
                "id": p.get("id", ""),
                "title": p.get("title", ""),
                "summary": p.get("summary", ""),
                "published": p.get("published", ""),
                "categories": p.get("categories", []),
                "citation_count": p.get("citation_count", None),
                "semantic_score": p.get("semantic_score", p.get("tfidf_score", 0.0)),
                "url": p.get("url", ""),
            }
        )

    try:
        prompt = OPENAI_ARXIV_COMPARE_PROMPT_TEMPLATE.format(
            original_input=(original_input or "").strip() or "（空）",
            papers_json=json.dumps(compact_papers, ensure_ascii=False),
            w_relevance=f"{weights['relevance']:.2f}",
            w_novelty=f"{weights['novelty']:.2f}",
            w_recency=f"{weights['recency']:.2f}",
            w_citation=f"{weights['citation']:.2f}",
        )
    except Exception as e:
        raise RuntimeError(f"arXiv 对比 Prompt 模板格式化失败：{e}") from e

    client = _mk_client(api_key, base_url)
    raw = _chat_complete(
        client,
        model=model,
        messages=[
            {"role": "system", "content": OPENAI_ARXIV_COMPARE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        top_p=1.0,
        max_tokens=1200,
    )

    if not raw:
        return {
            "summary": "模型未返回对比结果。",
            "selected_ids": [],
            "top_matches": [],
            "used_model": model,
            "compare_limit": compare_limit,
        }

    json_text = _extract_first_json_object(raw)
    if not json_text:
        return {
            "summary": raw[:300],
            "selected_ids": [],
            "top_matches": [],
            "used_model": model,
            "compare_limit": compare_limit,
        }

    try:
        parsed = json.loads(json_text)
    except Exception:
        return {
            "summary": raw[:300],
            "selected_ids": [],
            "top_matches": [],
            "used_model": model,
            "compare_limit": compare_limit,
        }

    if not isinstance(parsed, dict):
        return {
            "summary": "对比结果格式无效。",
            "selected_ids": [],
            "top_matches": [],
            "used_model": model,
            "compare_limit": compare_limit,
        }
    result = _normalize_compare_payload(parsed, weights)
    result["used_model"] = model
    result["compare_limit"] = compare_limit
    return result


def organize_selected_papers_report(
    settings: Dict[str, Any],
    original_input: str,
    compare_result: Dict[str, Any],
    selected_papers: List[Dict[str, Any]],
) -> str:
    """Third OpenAI prompt: organize selected papers into a Chinese markdown report."""
    profile = _active_profile(settings)
    openai_cfg = _agent_cfg(profile, "openai")
    weights = _compare_weights(settings)

    api_key = str(openai_cfg.get("api_key") or "").strip()
    base_url = str(openai_cfg.get("base_url") or "").strip()
    model = str(openai_cfg.get("model") or "").strip()
    if not model:
        raise RuntimeError("OpenAI model 为空（请在设置里选择模型）")
    if not api_key:
        raise RuntimeError("OpenAI API Key 为空（请在设置里配置）")

    compact_papers: List[Dict[str, Any]] = []
    for p in (selected_papers or [])[:10]:
        if not isinstance(p, dict):
            continue
        compact_papers.append(
            {
                "id": p.get("id", ""),
                "title": p.get("title", ""),
                "summary": p.get("summary", ""),
                "published": p.get("published", ""),
                "citation_count": p.get("citation_count", None),
                "url": p.get("url", ""),
            }
        )

    try:
        prompt = OPENAI_ARXIV_ORGANIZE_PROMPT_TEMPLATE.format(
            original_input=(original_input or "").strip() or "（空）",
            w_relevance=f"{weights['relevance']:.2f}",
            w_novelty=f"{weights['novelty']:.2f}",
            w_recency=f"{weights['recency']:.2f}",
            w_citation=f"{weights['citation']:.2f}",
            compare_result_json=json.dumps(compare_result or {}, ensure_ascii=False),
            papers_json=json.dumps(compact_papers, ensure_ascii=False),
        )
    except Exception as e:
        raise RuntimeError(f"arXiv 整理 Prompt 模板格式化失败：{e}") from e

    client = _mk_client(api_key, base_url)
    report = _chat_complete(
        client,
        model=model,
        messages=[
            {"role": "system", "content": OPENAI_ARXIV_ORGANIZE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        top_p=1.0,
        max_tokens=1800,
    )

    return (report or "").strip() or "论文整理结果为空。"


def submit_init_prompts(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    新建对话时调用：仅向 OpenAI 发送一次初始化 prompt。
    返回：
      {
        "openai_init_reply": "...",
        "errors": {"openai": "..."}
      }
    """
    profile = _active_profile(settings)
    openai_cfg = _agent_cfg(profile, "openai")

    result: Dict[str, Any] = {"openai_init_reply": "", "errors": {}}

    # ---- OpenAI init ----
    try:
        api_key = str(openai_cfg.get("api_key") or "").strip()
        base_url = str(openai_cfg.get("base_url") or "").strip()
        model = str(openai_cfg.get("model") or "").strip()
        if not model:
            raise RuntimeError("OpenAI model 为空（请在设置里选择模型）")
        if not api_key:
            raise RuntimeError("OpenAI API Key 为空（请在设置里配置）")

        client = _mk_client(api_key, base_url)
        msg = [
            {"role": "system", "content": OPENAI_SYSTEM_PROMPT},
            {"role": "user", "content": OPENAI_INIT_PROMPT},
        ]
        result["openai_init_reply"] = _chat_complete(
            client,
            model=model,
            messages=msg,
            temperature=float(openai_cfg.get("temperature", 0.2) or 0.2),
            top_p=float(openai_cfg.get("top_p", 1.0) or 1.0),
            max_tokens=int(openai_cfg.get("max_tokens", 2048) or 2048),
        )
    except Exception as e:
        result["errors"]["openai"] = str(e)

    return result


def run_dual_turn(
    settings: Dict[str, Any],
    history: List[Dict[str, str]],
    user_text: str,
    init_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    每次发送调用（OpenAI-only）：
    1) 基于历史 + 用户输入调用 OpenAI
    2) 返回 (openai_final, "")
    """
    init_meta = init_meta or {}
    profile = _active_profile(settings)
    openai_cfg = _agent_cfg(profile, "openai")

    api_key = str(openai_cfg.get("api_key") or "").strip()
    base_url = str(openai_cfg.get("base_url") or "").strip()
    model = str(openai_cfg.get("model") or "gpt-4o-mini").strip()
    if not api_key:
        raise RuntimeError("OpenAI API Key 为空")

    client = _mk_client(api_key, base_url)

    oa_messages: List[Dict[str, str]] = [{"role": "system", "content": OPENAI_SYSTEM_PROMPT}]
    if init_meta.get("openai_init_reply"):
        oa_messages.append({"role": "system", "content": f"（初始化信息）{init_meta['openai_init_reply']}"})
    compare_result = init_meta.get("arxiv_compare_result")
    if isinstance(compare_result, dict):
        cmp_summary = str(compare_result.get("summary") or "").strip()
        if cmp_summary:
            oa_messages.append({"role": "system", "content": f"（初始化论文筛选结论）{cmp_summary}"})

    organized_report = str(init_meta.get("arxiv_organized_report") or "").strip()
    if organized_report:
        oa_messages.append({"role": "system", "content": f"（初始化论文整理报告）\n{organized_report}"})

    selected_papers = init_meta.get("arxiv_selected_papers")
    if isinstance(selected_papers, list) and selected_papers:
        lines: List[str] = []
        for i, p in enumerate(selected_papers[:5], start=1):
            if not isinstance(p, dict):
                continue
            title = str(p.get("title") or "").strip()
            summary = str(p.get("summary") or "").replace("\r", " ").replace("\n", " ").strip()
            if len(summary) > 260:
                summary = summary[:260] + "…"
            if title or summary:
                lines.append(f"[{i}] {title}\n摘要: {summary}")
        if lines:
            oa_messages.append(
                {
                    "role": "system",
                    "content": "（可分析的已筛选论文列表）\n" + "\n\n".join(lines),
                }
            )

    oa_messages.extend(history)
    oa_messages.append({"role": "user", "content": user_text})

    final = _chat_complete(
        client,
        model=model,
        messages=oa_messages,
        temperature=float(openai_cfg.get("temperature", 0.2) or 0.2),
        top_p=float(openai_cfg.get("top_p", 1.0) or 1.0),
        max_tokens=int(openai_cfg.get("max_tokens", 2048) or 2048),
    )
    return final, ""
