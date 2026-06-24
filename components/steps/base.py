"""
BaseStepHandler — 所有 Step Handler 的基类。

每个 Handler 接收 step dict 和 Context，返回 StepResult。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from components.Context import Context


@dataclass
class StepResult:
    """一步执行的结果。"""
    step_id: str = ""
    step_type: str = ""
    status: str = "unknown"        # passed / failed / skipped / error
    send: str = ""                 # 发送内容（变量替换后）
    response: str = ""             # 原始响应
    elapsed_ms: int = 0            # 耗时
    error: str = ""                # 错误信息
    capture: dict = field(default_factory=dict)  # 提取的变量

    @property
    def ok(self) -> bool:
        return self.status == "passed"

    @property
    def is_skip(self) -> bool:
        return self.status == "skipped"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def skipped(cls, step_id: str = "") -> "StepResult":
        return cls(step_id=step_id, status="skipped")

    @classmethod
    def from_error(cls, step_id: str, error: str, **kw) -> "StepResult":
        return cls(step_id=step_id, status="error", error=error, **kw)


class BaseStepHandler:
    """Step Handler 基类。"""

    def __init__(self, ctx: Context, action_handler: Any = None):
        self.ctx = ctx
        self.action_handler = action_handler

    def execute(self, step: dict) -> StepResult:
        """执行一步。子类必须实现此方法。"""
        raise NotImplementedError

    def resolve(self, text: str) -> str:
        """快捷方法：对文本执行变量替换。"""
        from utils.TemplateEngine import TemplateEngine
        return TemplateEngine(self.ctx).resolve(text)
