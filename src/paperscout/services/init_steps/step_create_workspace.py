from __future__ import annotations

import os

from paperscout.config.settings import app_data_dir
from paperscout.services.init_steps.base import InitContext, InitStep


class StepCreateWorkspace(InitStep):
    name = "创建工作目录"

    def run(self, ctx: InitContext) -> None:
        workspace_root = os.path.join(app_data_dir(), "sessions")
        session_dir = os.path.join(workspace_root, ctx.thread_id)
        os.makedirs(session_dir, exist_ok=True)
        ctx.data["session_dir"] = session_dir
