"""
SerialStepHandler — 执行串口 AT 命令和等待串口输出的 Step Handler。
"""

from __future__ import annotations

import re
import time

from components.steps.base import BaseStepHandler, StepResult
from utils.TemplateEngine import TemplateEngine


class _SerialBaseStepHandler(BaseStepHandler):
    """串口步骤共享执行逻辑。"""

    step_type = "serial"

    def _execute_serial(self, step: dict, cmd_str: str, display_send: str,
                        require_expect: bool = False,
                        hex_mode: bool = False) -> StepResult:
        step_id = step.get("id", "")
        device_name = step.get("device", "")
        raw_expect = step.get("expect", step.get("expected_responses", []))
        timeout = _as_float(step.get("timeout", 3000), 3000.0)
        engine = TemplateEngine(self.ctx)

        devices = self.ctx.get("devices", {})
        if not device_name or device_name not in devices:
            return StepResult.skipped(step_id)

        device = self.ctx.get(f"_runtime.devices.{device_name}")
        if device is None:
            return StepResult.from_error(
                step_id, f"No runtime device instance for '{device_name}'",
                step_type=self.step_type, send=display_send)

        expected = _resolve_expected(engine, raw_expect)
        if require_expect and not expected:
            return StepResult.from_error(
                step_id, "serial_wait requires non-empty expect/expected_responses",
                step_type=self.step_type, send=display_send)

        try:
            t0 = time.time()
            result = device.send_command(
                cmd_str,
                timeout=timeout / 1000,
                hex_mode=hex_mode,
                expected_responses=expected,
            )
            elapsed = int((time.time() - t0) * 1000)

            response = result.get("response", "")
            success = result.get("success", False)
            matched = result.get("matched", [])
            capture = _extract_capture(engine, step, response)

            status = "passed" if success else "failed"
            error = "" if success else (
                f"Expected {expected} not fully matched "
                f"(matched {len(matched)}/{len(expected)})")

            return StepResult(
                step_id=step_id,
                step_type=self.step_type,
                status=status,
                send=display_send,
                response=response,
                elapsed_ms=elapsed,
                error=error,
                capture=capture,
            )

        except Exception as e:
            return StepResult.from_error(
                step_id, str(e), step_type=self.step_type, send=display_send)


class SerialStepHandler(_SerialBaseStepHandler):
    """处理 type: serial 的步骤。"""

    step_type = "serial"

    def execute(self, step: dict) -> StepResult:
        engine = TemplateEngine(self.ctx)
        raw_cmd = step.get("send", step.get("command", ""))
        cmd_str = engine.resolve(raw_cmd)
        hex_mode = step.get("encoding") == "hex" or step.get("hex_mode", False)
        return self._execute_serial(step, cmd_str, cmd_str, hex_mode=hex_mode)


class SerialWaitStepHandler(_SerialBaseStepHandler):
    """处理 type: serial_wait 的步骤：不发送指令，只等待串口响应。"""

    step_type = "serial_wait"

    def execute(self, step: dict) -> StepResult:
        return self._execute_serial(
            step, "", "SERIAL_WAIT", require_expect=True, hex_mode=False)


def _resolve_expected(engine: TemplateEngine, raw_expect) -> list[str]:
    if isinstance(raw_expect, list):
        return [engine.resolve(e) for e in raw_expect]
    if isinstance(raw_expect, str) and raw_expect:
        return [engine.resolve(raw_expect)]
    return []


def _extract_capture(engine: TemplateEngine, step: dict, response: str) -> dict:
    capture = {}
    raw_capture = step.get("capture", step.get("variables", {}))
    if isinstance(raw_capture, dict):
        for key, pattern in raw_capture.items():
            m = re.search(engine.resolve(pattern), response)
            if m:
                val = m.group(1)
                try:
                    capture[key] = int(val)
                except ValueError:
                    try:
                        capture[key] = float(val)
                    except ValueError:
                        capture[key] = val
    return capture


def _as_float(value, default: float) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
