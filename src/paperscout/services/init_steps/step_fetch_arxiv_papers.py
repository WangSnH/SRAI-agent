from __future__ import annotations

import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Dict, List

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
            max_results = self._safe_int(arxiv.get("max_results"), 20)
            max_results = max(1, min(100, max_results))

            target_count = max(max_results // 2, 5)
            fetch_count = max(max_results, target_count * 2)
            fetch_count = max(10, min(100, fetch_count))

            papers = self._fetch_arxiv(categories, keywords, fetch_count)
            filtered = self._keyword_filter(papers, keywords)
            ranked_filtered = self._rank_tfidf(filtered, keywords)
            ranked_all = self._rank_tfidf(papers, keywords)

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

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{1,}", (text or "").lower())

    def _rank_tfidf(self, papers: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
        if not papers:
            return []

        docs = [self._tokenize(f"{p.get('title', '')} {p.get('summary', '')}") for p in papers]
        query_tokens = self._tokenize(" ".join(keywords))
        if not query_tokens:
            return papers

        n_docs = len(docs)
        df = Counter()
        for tokens in docs:
            for t in set(tokens):
                df[t] += 1

        def idf(token: str) -> float:
            return math.log((1 + n_docs) / (1 + df.get(token, 0))) + 1.0

        def vec(tokens: List[str]) -> Dict[str, float]:
            if not tokens:
                return {}
            tf = Counter(tokens)
            total = float(len(tokens))
            return {t: (c / total) * idf(t) for t, c in tf.items()}

        qv = vec(query_tokens)

        def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
            if not a or not b:
                return 0.0
            dot = 0.0
            for k, v in a.items():
                dot += v * b.get(k, 0.0)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            if na == 0.0 or nb == 0.0:
                return 0.0
            return dot / (na * nb)

        scored: List[Dict[str, Any]] = []
        for p, tokens in zip(papers, docs):
            score = cosine(vec(tokens), qv)
            item = dict(p)
            item["tfidf_score"] = round(score, 6)
            scored.append(item)

        scored.sort(key=lambda x: float(x.get("tfidf_score", 0.0)), reverse=True)
        return scored
