"""
ActionBatchStepHandler — 批量执行 actions 的 Step Handler。

不发送外部 I/O，只把 step.actions 委托给现有 ActionHandler 执行。
"""

from __future__ import annotations

import json
import time

from components.steps.base import BaseStepHandler, StepResult


class ActionBatchStepHandler(BaseStepHandler):
    """处理 type: action_batch 的步骤（纯 action 执行，无 I/O）。"""

    def execute(self, step: dict) -> StepResult:
        step_id = step.get("id", "")
        actions = step.get("actions", [])
        if not actions:
            return StepResult(
                step_id=step_id, step_type="action_batch", status="passed"
            )

        if self.action_handler is None:
            return StepResult.from_error(
                step_id,
                "ActionHandler is not available for action_batch",
                step_type="action_batch",
                send=f"{len(actions)} actions",
            )

        device_name = step.get("device", "")
        context = {
            "device": self.ctx.get(f"_runtime.devices.{device_name}") if device_name else None,
            "device_name": device_name,
            "cmd_str": step.get("send", step.get("command", "")),
            "expected_responses": step.get("expect", step.get("expected_responses", [])),
            "priority": step.get("priority", 0),
            "completion_rules": step.get("completion_rules"),
            "_action_results": [],
        }
        command = dict(step)
        command["actions"] = actions

        t0 = time.time()
        ok = self.action_handler.handle_actions(
            command, "", "actions", context)
        elapsed = int((time.time() - t0) * 1000)
        action_results = context.get("_action_results", [])
        failed = [r for r in action_results if r.get("status") != "passed"]
        error = "" if ok else "; ".join(
            f"{r.get('action', 'unknown')}: {r.get('detail', r.get('status', 'failed'))}"
            for r in failed
        ) or "One or more actions failed"

        return StepResult(
            step_id=step_id,
            step_type="action_batch",
            status="passed" if ok else "failed",
            send=f"{len(actions)} actions",
            response=json.dumps(action_results, ensure_ascii=False, indent=2),
            elapsed_ms=elapsed,
            error=error,
            capture={"actions": action_results},
        )
