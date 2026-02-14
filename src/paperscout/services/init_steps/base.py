from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class InitContext:
    """
    初始化上下文：贯穿整个pipeline，步骤之间通过 ctx.data 传递信息。
    """
    settings: Dict[str, Any]
    feature_key: str
    thread_id: str
    thread_name: str
    original_input: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


class InitStep:
    """
    初始化步骤抽象类：每一步实现 run(ctx)。
    需要对外显示的进度/状态由 worker 在调用前后 emit。
    """

    name: str = "UnnamedStep"

    def run(self, ctx: InitContext) -> None:
        raise NotImplementedError
