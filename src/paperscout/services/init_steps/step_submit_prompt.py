from __future__ import annotations

from paperscout.services.init_steps.base import InitContext, InitStep
from paperscout.services.dual_orchestrator import generate_arxiv_api_payload


class StepSubmitPrompt(InitStep):
    name = "调用 OpenAI 生成 arXiv 检索参数"

    def run(self, ctx: InitContext) -> None:
        # 调用第一个 OpenAI prompt，生成 arXiv API 参数
        # 这是关键步骤，失败需要向上抛出异常让管线中止
        arxiv_payload = generate_arxiv_api_payload(
            settings=ctx.settings,
            feature_key=ctx.feature_key,
            thread_name=ctx.thread_name,
            original_input=ctx.original_input,
        )
        ctx.data["arxiv_api_payload"] = arxiv_payload
        ctx.data["openai_init_reply"] = "arXiv 检索参数已生成。"
