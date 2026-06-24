"""
WaitStepHandler — 单纯的等待步骤。
"""

from __future__ import annotations

import time

from components.steps.base import BaseStepHandler, StepResult


class WaitStepHandler(BaseStepHandler):
    """处理 type: wait 的步骤（纯延时）。"""

    def execute(self, step: dict) -> StepResult:
        step_id = step.get("id", "")
        duration = step.get("duration", 1000)  # 毫秒

        if isinstance(duration, dict):
            duration = duration.get("duration", 1000)  # 兼容旧 { wait: { duration: ... } }

        time.sleep(float(duration) / 1000)

        return StepResult(
            step_id=step_id,
            step_type="wait",
            status="passed",
            send=f"wait {duration}ms",
            elapsed_ms=int(duration),
        )
