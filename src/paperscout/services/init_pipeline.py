from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from paperscout.config.settings import get_system_param_int
from paperscout.services.init_steps.base import InitContext, InitStep


@dataclass
class InitResult:
    ok: bool
    summary: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


def build_steps() -> List[InitStep]:
    """
    构建初始化步骤列表（可扩展）。
    后续你可以把多个 prompt 调用、预抓取、缓存、日志、DB 等都塞进来。
    """
    from paperscout.services.init_steps.step_init_metadata import StepInitMetadata
    from paperscout.services.init_steps.step_create_workspace import StepCreateWorkspace
    from paperscout.services.init_steps.step_submit_prompt import StepSubmitPrompt
    from paperscout.services.init_steps.step_fetch_arxiv_papers import StepFetchArxivPapers
    from paperscout.services.init_steps.step_compare_arxiv_abstracts import StepCompareArxivAbstracts
    from paperscout.services.init_steps.step_organize_selected_papers import StepOrganizeSelectedPapers

    return [
        StepInitMetadata(),
        StepCreateWorkspace(),
        StepSubmitPrompt(),
        StepFetchArxivPapers(),
        StepCompareArxivAbstracts(),
        StepOrganizeSelectedPapers(),
        # TODO: StepLoadUserCriteria()
        # TODO: StepBuildTaskPlanWithGPT()
    ]


def run_init_pipeline(ctx: InitContext, steps: Optional[List[InitStep]] = None) -> InitResult:
    """
    无 UI 的纯执行版本（不负责逐步进度）。
    UI 逐步进度目前由 InitPipelineWorker 自己迭代 steps 并 emit。
    """
    steps = steps or build_steps()
    for step in steps:
        step.run(ctx)
    return InitResult(ok=True, summary=make_summary(ctx), data=ctx.data)


def make_summary(ctx: InitContext) -> str:
    """初始化完成后的汇总输出（显示在聊天里）。

    目前主要汇总：OpenAI 初始化返回与论文筛选结果。
    """
    organized = str(ctx.data.get("arxiv_organized_report") or "").strip()
    oa = str(ctx.data.get("openai_init_reply") or "").strip()
    fetched = int(ctx.data.get("arxiv_total_fetched") or 0)
    filtered = int(ctx.data.get("arxiv_keyword_filtered") or 0)
    selected = int(ctx.data.get("arxiv_selected_count") or 0)
    top_n = get_system_param_int(ctx.settings, "final_output_paper_count", 5, 1, 50)
    selected_papers = ctx.data.get("arxiv_selected_papers")
    compare_result = ctx.data.get("arxiv_compare_result")
    errs = ctx.data.get("init_errors") or {}

    if organized:
        return organized

    lines = ["初始化完成。"]
    if isinstance(errs, dict) and errs:
        lines.append(f"⚠ 初始化提示：{errs}")

    if fetched or filtered or selected:
        lines.append(f"arXiv 抓取：{fetched} 篇；关键词过滤后：{filtered} 篇；预筛选入选：{selected} 篇")
    if isinstance(selected_papers, list) and selected_papers:
        top_titles = [str(x.get("title") or "").strip() for x in selected_papers[:top_n] if isinstance(x, dict)]
        top_titles = [t for t in top_titles if t]
        if top_titles:
            lines.append("Top 论文：" + "；".join(top_titles))

    if isinstance(compare_result, dict):
        cmp_summary = str(compare_result.get("summary") or "").strip()
        if cmp_summary:
            lines.append(f"对比结论：{cmp_summary}")
        top_matches = compare_result.get("top_matches")
        if isinstance(top_matches, list) and top_matches:
            best = []
            for item in top_matches[:top_n]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("id") or "").strip()
                score = item.get("score", 0.0)
                if title:
                    best.append(f"{title}({score})")
            if best:
                lines.append(f"评分Top{top_n}：" + "；".join(best))

    def clip(s: str, n: int = 240) -> str:
        s = s.replace("\r", "").strip()
        return s if len(s) <= n else (s[:n] + "…")

    if oa:
        lines.append(f"OpenAI 初始化：{clip(oa)}")

    return "\n".join(lines)

