from __future__ import annotations

from datetime import datetime

from paperscout.services.init_steps.base import InitContext, InitStep


class StepInitMetadata(InitStep):
    name = "初始化元信息"

    def run(self, ctx: InitContext) -> None:
        # TODO: 后续可写入本地db/json，或写到 settings["ui"] 的 thread meta
        ctx.data["created_at"] = datetime.now().isoformat(timespec="seconds")
        ctx.data["feature_key"] = ctx.feature_key
        ctx.data["thread_id"] = ctx.thread_id
        ctx.data["thread_name"] = ctx.thread_name
        ctx.data["original_input"] = (ctx.original_input or "").strip()
        # pass
