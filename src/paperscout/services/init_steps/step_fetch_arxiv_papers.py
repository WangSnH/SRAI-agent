from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import math
import re
from collections import Counter
from typing import Any, Dict, List

from paperscout.config.settings import (
    SENTENCE_TRANSFORMER_MODEL_OPTIONS,
    app_data_dir,
    get_system_param_choice,
    get_system_param_int,
)
from paperscout.services.init_steps.base import InitContext, InitStep


class StepFetchArxivPapers(InitStep):
    name = "调用 arXiv API 并筛选高质量论文"

    _st_model_cache: Dict[str, Any] = {}
    _ST_MODEL_CACHE_MAX_SIZE = 2  # Limit to avoid memory explosion

    def __init__(self):
        self._last_rank_backend = "bm25"
        self._last_semantic_model = ""

    def run(self, ctx: InitContext) -> None:
        try:
            payload = ctx.data.get("arxiv_api_payload") or {}
            arxiv = payload.get("arxiv") if isinstance(payload, dict) else {}
            arxiv = arxiv if isinstance(arxiv, dict) else {}

            categories = self._norm_list(arxiv.get("categories"), ["cs.AI", "cs.LG"])
            categories = categories[:2]
            keywords = self._norm_list(
                arxiv.get("keywords"),
                ["large language model", "transformer"],
            )
            keywords = keywords[:2]
            configured_final_count = get_system_param_int(
                ctx.settings,
                "final_output_paper_count",
                5,
                1,
                50,
            )
            configured_max_results = get_system_param_int(
                ctx.settings,
                "arxiv_fetch_max_results",
                20,
                5,
                300,
            )
            max_results = self._safe_int(arxiv.get("max_results"), configured_max_results)
            max_results = max(configured_final_count, min(300, max_results))

            target_count = configured_final_count
            fetch_count = max(max_results * 4, target_count * 12, 80)
            fetch_count = max(40, min(300, fetch_count))
            coarse_target_count = max(max_results, target_count * 6, 30)
            coarse_target_count = max(target_count, min(120, coarse_target_count))
            query_text = str(ctx.data.get("original_input_en") or "").strip()
            if not query_text:
                query_text = str(ctx.original_input or "").strip() or " ".join(keywords)

            papers, fetch_meta = self._fetch_arxiv_resilient(categories, keywords, fetch_count)
            if papers:
                self._save_cache(papers)
            else:
                cached = self._load_cache()
                if cached:
                    papers = cached
                    fetch_meta["source"] = "cache"
                    fetch_meta["used_cache"] = True

            filtered = self._keyword_filter(papers, keywords)

            coarse_ranked = self._rank_keyword_overlap(papers, query_text)
            coarse_candidates = coarse_ranked[:coarse_target_count]
            semantic_model = get_system_param_choice(
                ctx.settings,
                "sentence_transformer_model",
                "BAAI/bge-large-en-v1.5",
                SENTENCE_TRANSFORMER_MODEL_OPTIONS,
            )
            fine_ranked = self._rank_semantic(coarse_candidates, query_text, semantic_model)
            fine_backend = str(getattr(self, "_last_rank_backend", "bm25") or "bm25")
            fine_model = str(getattr(self, "_last_semantic_model", "") or "").strip()

            selected: List[Dict[str, Any]] = []
            seen_ids = set()

            for p in fine_ranked:
                pid = str(p.get("id") or p.get("url") or p.get("title") or "").strip()
                if pid and pid not in seen_ids:
                    selected.append(p)
                    seen_ids.add(pid)
                if len(selected) >= coarse_target_count:
                    break

            if len(selected) < coarse_target_count:
                for p in coarse_ranked:
                    pid = str(p.get("id") or p.get("url") or p.get("title") or "").strip()
                    if pid and pid not in seen_ids:
                        selected.append(p)
                        seen_ids.add(pid)
                    if len(selected) >= coarse_target_count:
                        break

            ctx.data["arxiv_fetch_config"] = {
                "categories": categories,
                "keywords": keywords,
                "semantic_query": query_text,
                "final_output_paper_count": target_count,
                "max_results": max_results,
                "target_count": target_count,
                "coarse_target_count": coarse_target_count,
                "fetch_count": fetch_count,
                "fetch_source": fetch_meta.get("source", "unknown"),
                "fetch_errors": fetch_meta.get("errors", []),
                "compare_algorithm": f"coarse=bm25; fine={fine_backend}{f'({fine_model})' if fine_model else ''}",
                "fine_algorithm": f"{fine_backend}{f' ({fine_model})' if fine_model else ''}",
                "sentence_transformer_model": semantic_model,
            }
            ctx.data["arxiv_total_fetched"] = len(papers)
            ctx.data["arxiv_keyword_filtered"] = len(filtered)
            ctx.data["arxiv_selected_count"] = len(selected)
            ctx.data["arxiv_selected_papers"] = selected

            if fetch_meta.get("used_cache"):
                errs = ctx.data.get("init_errors", {})
                errs = errs if isinstance(errs, dict) else {}
                errs["arxiv_fetch"] = "arXiv 网络超时，已回退本地缓存候选论文。"
                ctx.data["init_errors"] = errs

        except Exception as e:
            errs = ctx.data.get("init_errors", {})
            errs = errs if isinstance(errs, dict) else {}
            errs["arxiv_fetch"] = str(e)
            ctx.data["init_errors"] = errs
            ctx.data.setdefault("arxiv_selected_papers", [])
            ctx.data.setdefault("arxiv_selected_count", 0)

    @staticmethod
    def _norm_list(value: Any, default: List[str]) -> List[str]:
        if not isinstance(value, list):
            return default
        out = [str(x).strip() for x in value if str(x).strip()]
        return out or default

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _build_query(categories: List[str], keywords: List[str]) -> str:
        cat_q = " OR ".join(f"cat:{c}" for c in categories)
        kw_q = " OR ".join(f'all:"{k}"' for k in keywords)
        if cat_q and kw_q:
            return f"({cat_q}) AND ({kw_q})"
        if cat_q:
            return cat_q
        return kw_q or "all:machine learning"

    def _fetch_arxiv_by_query(
        self,
        query: str,
        fetch_count: int,
        timeout_sec: int = 20,
        sort_by: str = "relevance",
        sort_order: str = "descending",
    ) -> List[Dict[str, Any]]:
        params = {
            "search_query": query,
            "start": 0,
            "max_results": fetch_count,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, headers={"User-Agent": "PaperScout/0.1"})
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        papers: List[Dict[str, Any]] = []
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
            paper_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
            published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()

            authors = [
                (a.findtext("atom:name", default="", namespaces=ns) or "").strip()
                for a in entry.findall("atom:author", ns)
            ]
            authors = [x for x in authors if x]

            categories = [
                (c.attrib.get("term") or "").strip()
                for c in entry.findall("atom:category", ns)
            ]
            categories = [x for x in categories if x]

            link = ""
            for lk in entry.findall("atom:link", ns):
                href = (lk.attrib.get("href") or "").strip()
                rel = (lk.attrib.get("rel") or "").strip()
                if rel == "alternate" and href:
                    link = href
                    break
            if not link:
                link = paper_id

            papers.append(
                {
                    "id": paper_id,
                    "title": title,
                    "summary": summary,
                    "published": published,
                    "citation_count": None,
                    "authors": authors,
                    "categories": categories,
                    "url": link,
                }
            )

        return papers

    @staticmethod
    def _merge_unique_papers(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for group in groups:
            for p in group:
                pid = str(p.get("id") or p.get("url") or p.get("title") or "").strip()
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                out.append(p)
        return out

    def _fetch_arxiv_resilient(
        self,
        categories: List[str],
        keywords: List[str],
        fetch_count: int,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        errors: List[str] = []

        strict_categories = categories[:2] if categories else ["cs.AI"]
        strict_keywords = keywords[:2] if keywords else ["machine learning"]
        fallback_categories = strict_categories[:1]
        fallback_keywords = strict_keywords[:1]

        strict_query = self._build_query(strict_categories, strict_keywords)
        fallback_query = self._build_query(fallback_categories, fallback_keywords)

        plans = [
            ("strict_2c2k", strict_query, fetch_count, [20, 30, 45]),
            ("fallback_1c1k", fallback_query, max(fetch_count, 20), [20, 35]),
        ]

        for label, query, count, timeouts in plans:
            if not str(query or "").strip():
                continue
            for timeout_sec in timeouts:
                try:
                    relevance_count = max(1, int(count * 0.7))
                    recency_count = max(1, int(count) - relevance_count)

                    relevance_papers = self._fetch_arxiv_by_query(
                        query=query,
                        fetch_count=max(5, min(300, relevance_count)),
                        timeout_sec=int(timeout_sec),
                        sort_by="relevance",
                        sort_order="descending",
                    )
                    recency_papers = self._fetch_arxiv_by_query(
                        query=query,
                        fetch_count=max(3, min(300, recency_count)),
                        timeout_sec=int(timeout_sec),
                        sort_by="submittedDate",
                        sort_order="descending",
                    )

                    papers = self._merge_unique_papers(relevance_papers, recency_papers)
                    if papers:
                        return papers, {"source": label, "errors": errors, "used_cache": False}
                    errors.append(f"{label}:empty")
                except Exception as e:
                    errors.append(f"{label}:t{timeout_sec}:{e}")
                    time.sleep(0.15)

        return [], {"source": "none", "errors": errors, "used_cache": False}

    @staticmethod
    def _cache_path() -> str:
        return os.path.join(app_data_dir(), "arxiv_fallback_cache.json")

    def _save_cache(self, papers: List[Dict[str, Any]]) -> None:
        try:
            path = self._cache_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = {
                "version": 1,
                "saved_at": time.time(),
                "papers": [p for p in papers[:80] if isinstance(p, dict)],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_cache(self, max_age_hours: float = 24.0) -> List[Dict[str, Any]]:
        try:
            path = self._cache_path()
            if not os.path.exists(path):
                return []
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                return []
            # Check expiration
            saved_at = float(payload.get("saved_at", 0) or 0)
            if saved_at > 0 and (time.time() - saved_at) > max_age_hours * 3600:
                return []  # Cache expired
            papers = payload.get("papers") if isinstance(payload, dict) else []
            return [p for p in (papers or []) if isinstance(p, dict)]
        except Exception:
            return []

    @staticmethod
    def _keyword_filter(papers: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
        kws = [k.lower().strip() for k in keywords if str(k).strip()]
        if not kws:
            return papers

        out: List[Dict[str, Any]] = []
        for p in papers:
            text = f"{p.get('title', '')} {p.get('summary', '')}".lower()
            if any(k in text for k in kws):
                out.append(p)
        return out

    def _rank_semantic(self, papers: List[Dict[str, Any]], query_text: str, model_name: str) -> List[Dict[str, Any]]:
        if not papers:
            return []

        clean_query = str(query_text or "").strip()
        if not clean_query:
            return papers

        docs = [f"{p.get('title', '')}\n{p.get('summary', '')}".strip() for p in papers]

        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            self._last_rank_backend = "bm25"
            self._last_semantic_model = ""
            return self._rank_keyword_overlap(papers, clean_query)

        try:
            selected_model = str(model_name or "BAAI/bge-large-en-v1.5").strip()
            if selected_model not in SENTENCE_TRANSFORMER_MODEL_OPTIONS:
                selected_model = "BAAI/bge-large-en-v1.5"
            model = self._st_model_cache.get(selected_model)
            if model is None:
                # Evict oldest entry if cache is full
                if len(self._st_model_cache) >= self._ST_MODEL_CACHE_MAX_SIZE:
                    oldest_key = next(iter(self._st_model_cache))
                    del self._st_model_cache[oldest_key]
                model = SentenceTransformer(selected_model)
                self._st_model_cache[selected_model] = model
            embeddings = model.encode([clean_query] + docs, normalize_embeddings=True)
            query_vec = embeddings[0]
            doc_vecs = embeddings[1:]
            self._last_rank_backend = "sentence-transformers"
            self._last_semantic_model = selected_model
        except Exception:
            self._last_rank_backend = "bm25"
            self._last_semantic_model = ""
            return self._rank_keyword_overlap(papers, clean_query)

        scored: List[Dict[str, Any]] = []
        for p, vec in zip(papers, doc_vecs):
            score = float(query_vec @ vec)
            item = dict(p)
            item["semantic_score"] = round(score, 6)
            scored.append(item)

        scored.sort(key=lambda x: float(x.get("semantic_score", 0.0)), reverse=True)
        return scored

    @staticmethod
    def _rank_keyword_overlap(papers: List[Dict[str, Any]], query_text: str) -> List[Dict[str, Any]]:
        query_terms = StepFetchArxivPapers._tokenize_for_overlap(query_text)
        if not query_terms:
            return papers

        doc_terms: List[List[str]] = []
        title_terms: List[List[str]] = []
        for p in papers:
            title = str(p.get("title", "") or "")
            summary = str(p.get("summary", "") or "")
            title_tokens = StepFetchArxivPapers._tokenize_for_overlap(title)
            body_tokens = StepFetchArxivPapers._tokenize_for_overlap(f"{title} {summary}")
            title_terms.append(title_tokens)
            doc_terms.append(body_tokens)

        if not doc_terms:
            return papers

        n_docs = len(doc_terms)
        avg_dl = sum(len(t) for t in doc_terms) / max(1, n_docs)
        df = Counter()
        for tokens in doc_terms:
            for token in set(tokens):
                df[token] += 1

        k1 = 1.2
        b = 0.75

        def idf(term: str) -> float:
            dft = df.get(term, 0)
            return math.log(1.0 + (n_docs - dft + 0.5) / (dft + 0.5))

        scored: List[Dict[str, Any]] = []
        for p, terms, t_terms in zip(papers, doc_terms, title_terms):
            if not terms:
                score = 0.0
            else:
                tf = Counter(terms)
                dl = len(terms)
                score = 0.0
                for term in query_terms:
                    freq = tf.get(term, 0)
                    if freq <= 0:
                        continue
                    denom = freq + k1 * (1.0 - b + b * dl / max(1e-6, avg_dl))
                    score += idf(term) * ((freq * (k1 + 1.0)) / max(1e-6, denom))

                if t_terms:
                    title_hit_ratio = sum(1 for term in set(query_terms) if term in set(t_terms)) / max(1, len(set(query_terms)))
                    score += 0.6 * title_hit_ratio

            item = dict(p)
            item["semantic_score"] = round(score, 6)
            scored.append(item)

        scored.sort(key=lambda x: float(x.get("semantic_score", 0.0)), reverse=True)
        return scored

    @staticmethod
    def _tokenize_for_overlap(text: str) -> List[str]:
        raw = str(text or "").lower()
        parts = re.findall(r"[a-z0-9][a-z0-9_\-]{1,}|[\u4e00-\u9fff]{1,}", raw)
        out: List[str] = []
        for part in parts:
            if re.fullmatch(r"[\u4e00-\u9fff]+", part):
                if len(part) <= 2:
                    out.append(part)
                else:
                    out.extend(part[i : i + 2] for i in range(len(part) - 1))
            else:
                out.append(part)
        return [x for x in out if x]
