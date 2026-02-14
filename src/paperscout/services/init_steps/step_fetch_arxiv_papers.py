from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import math
import re
from collections import Counter
from typing import Any, Dict, List

from paperscout.config.settings import get_system_param_int
from paperscout.services.init_steps.base import InitContext, InitStep


class StepFetchArxivPapers(InitStep):
    name = "调用 arXiv API 并筛选高质量论文"

    def run(self, ctx: InitContext) -> None:
        try:
            payload = ctx.data.get("arxiv_api_payload") or {}
            arxiv = payload.get("arxiv") if isinstance(payload, dict) else {}
            arxiv = arxiv if isinstance(arxiv, dict) else {}

            categories = self._norm_list(arxiv.get("categories"), ["cs.AI", "cs.LG"])
            keywords = self._norm_list(
                arxiv.get("keywords"),
                ["large language model", "transformer", "agent"],
            )
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
                100,
            )
            max_results = self._safe_int(arxiv.get("max_results"), configured_max_results)
            max_results = max(configured_final_count, min(100, max_results))

            target_count = configured_final_count
            fetch_count = max(max_results, target_count * 2)
            fetch_count = max(10, min(100, fetch_count))
            query_text = str(ctx.original_input or "").strip() or " ".join(keywords)

            papers = self._fetch_arxiv(categories, keywords, fetch_count)
            filtered = self._keyword_filter(papers, keywords)
            ranked_filtered = self._rank_semantic(filtered, query_text)
            ranked_all = self._rank_semantic(papers, query_text)

            selected: List[Dict[str, Any]] = []
            seen_ids = set()

            for p in ranked_filtered:
                pid = str(p.get("id") or p.get("url") or p.get("title") or "").strip()
                if pid and pid not in seen_ids:
                    selected.append(p)
                    seen_ids.add(pid)
                if len(selected) >= target_count:
                    break

            if len(selected) < target_count:
                for p in ranked_all:
                    pid = str(p.get("id") or p.get("url") or p.get("title") or "").strip()
                    if pid and pid not in seen_ids:
                        selected.append(p)
                        seen_ids.add(pid)
                    if len(selected) >= target_count:
                        break

            ctx.data["arxiv_fetch_config"] = {
                "categories": categories,
                "keywords": keywords,
                "semantic_query": query_text,
                "final_output_paper_count": target_count,
                "max_results": max_results,
                "target_count": target_count,
                "fetch_count": fetch_count,
            }
            ctx.data["arxiv_total_fetched"] = len(papers)
            ctx.data["arxiv_keyword_filtered"] = len(filtered)
            ctx.data["arxiv_selected_count"] = len(selected)
            ctx.data["arxiv_selected_papers"] = selected

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

    def _fetch_arxiv(self, categories: List[str], keywords: List[str], fetch_count: int) -> List[Dict[str, Any]]:
        query = self._build_query(categories, keywords)
        params = {
            "search_query": query,
            "start": 0,
            "max_results": fetch_count,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url, headers={"User-Agent": "PaperScout/0.1"})
        with urllib.request.urlopen(req, timeout=20) as resp:
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

    def _rank_semantic(self, papers: List[Dict[str, Any]], query_text: str) -> List[Dict[str, Any]]:
        if not papers:
            return []

        clean_query = str(query_text or "").strip()
        if not clean_query:
            return papers

        docs = [f"{p.get('title', '')}\n{p.get('summary', '')}".strip() for p in papers]

        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            return self._rank_keyword_overlap(papers, clean_query)

        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode([clean_query] + docs, normalize_embeddings=True)
            query_vec = embeddings[0]
            doc_vecs = embeddings[1:]
        except Exception:
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
