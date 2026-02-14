from __future__ import annotations

from typing import Any, Dict, List

from paperscout.config.settings import get_system_param_int
from paperscout.services.dual_orchestrator import compare_arxiv_abstracts_with_input
from paperscout.services.init_steps.base import InitContext, InitStep


class StepCompareArxivAbstracts(InitStep):
    name = "第二个Prompt：摘要与原始输入对比"

    def run(self, ctx: InitContext) -> None:
        final_count = get_system_param_int(ctx.settings, "final_output_paper_count", 5, 1, 50)
        papers = ctx.data.get("arxiv_selected_papers")
        papers = papers if isinstance(papers, list) else []

        original_input = str(ctx.data.get("original_input") or ctx.original_input or "").strip()
        if not original_input:
            original_input = str(ctx.thread_name or "").strip()

        try:
            result = compare_arxiv_abstracts_with_input(
                settings=ctx.settings,
                original_input=original_input,
                papers=[p for p in papers if isinstance(p, dict)],
            )
            result = result if isinstance(result, dict) else {}

            top_matches = result.get("top_matches")
            top_matches = top_matches if isinstance(top_matches, list) else []
            top_ids = []
            for item in top_matches:
                if isinstance(item, dict):
                    pid = str(item.get("id") or "").strip()
                    if pid:
                        top_ids.append(pid)

            selected_ids = result.get("selected_ids")
            selected_ids = selected_ids if isinstance(selected_ids, list) else []
            selected_ids = [str(x).strip() for x in selected_ids if str(x).strip()]

            preferred_ids = top_ids or selected_ids
            ordered: List[Dict[str, Any]] = []
            used = set()

            by_id = {}
            for p in papers:
                if not isinstance(p, dict):
                    continue
                pid = str(p.get("id") or "").strip()
                if pid:
                    by_id[pid] = p

            for pid in preferred_ids:
                p = by_id.get(pid)
                if p is not None and pid not in used:
                    ordered.append(p)
                    used.add(pid)

            if len(ordered) < final_count:
                for p in papers:
                    pid = str(p.get("id") or "").strip()
                    if pid and pid not in used:
                        ordered.append(p)
                        used.add(pid)
                    if len(ordered) >= final_count:
                        break

            final_selected = ordered[:final_count]
            if final_selected:
                ctx.data["arxiv_selected_papers"] = final_selected
                ctx.data["arxiv_selected_count"] = len(final_selected)

            ctx.data["arxiv_compare_result"] = result

        except Exception as e:
            errs = ctx.data.get("init_errors", {})
            errs = errs if isinstance(errs, dict) else {}
            errs["arxiv_compare"] = str(e)
            ctx.data["init_errors"] = errs
            ctx.data.setdefault("arxiv_compare_result", {})
