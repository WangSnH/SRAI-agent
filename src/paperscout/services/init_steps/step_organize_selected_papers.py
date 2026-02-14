from __future__ import annotations

from paperscout.services.dual_orchestrator import organize_selected_papers_report
from paperscout.services.init_steps.base import InitContext, InitStep


class StepOrganizeSelectedPapers(InitStep):
    name = "第三个Prompt：整理筛选论文并输出中文报告"

    def run(self, ctx: InitContext) -> None:
        original_input = str(ctx.data.get("original_input") or ctx.original_input or "").strip()
        compare_result = ctx.data.get("arxiv_compare_result")
        compare_result = compare_result if isinstance(compare_result, dict) else {}
        selected_papers = ctx.data.get("arxiv_selected_papers")
        selected_papers = [p for p in (selected_papers or []) if isinstance(p, dict)]

        try:
            report = organize_selected_papers_report(
                settings=ctx.settings,
                original_input=original_input,
                compare_result=compare_result,
                selected_papers=selected_papers,
            )
            ctx.data["arxiv_organized_report"] = report
        except Exception as e:
            errs = ctx.data.get("init_errors", {})
            errs = errs if isinstance(errs, dict) else {}
            errs["arxiv_organize"] = str(e)
            ctx.data["init_errors"] = errs
            ctx.data.setdefault("arxiv_organized_report", "")
