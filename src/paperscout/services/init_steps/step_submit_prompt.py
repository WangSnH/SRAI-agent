from __future__ import annotations

from paperscout.services.init_steps.base import InitContext, InitStep
from paperscout.services.dual_orchestrator import generate_arxiv_api_payload, translate_input_for_retrieval


class StepSubmitPrompt(InitStep):
    name = "调用 OpenAI 生成 arXiv 检索参数"

    def run(self, ctx: InitContext) -> None:
        normalized_input_en = translate_input_for_retrieval(
            settings=ctx.settings,
            text=ctx.original_input,
        )
        ctx.data["original_input_en"] = normalized_input_en

        # 调用第一个 OpenAI prompt，生成 arXiv API 参数
        # 这是关键步骤，失败需要向上抛出异常让管线中止
        arxiv_payload = generate_arxiv_api_payload(
            settings=ctx.settings,
            feature_key=ctx.feature_key,
            thread_name=ctx.thread_name,
            original_input=normalized_input_en or ctx.original_input,
        )
        ctx.data["arxiv_api_payload"] = arxiv_payload
        ctx.data["openai_init_reply"] = "arXiv 检索参数已生成。"
