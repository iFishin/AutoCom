"""
ScriptStepHandler — 执行本地脚本的 Step Handler。

用 subprocess.run() 执行命令，捕获 stdout/stderr/exit_code。
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from components.steps.base import BaseStepHandler, StepResult
from utils.TemplateEngine import TemplateEngine


class ScriptStepHandler(BaseStepHandler):
    """处理 type: script 的步骤。"""

    def execute(self, step: dict) -> StepResult:
        step_id = step.get("id", "")
        engine = TemplateEngine(self.ctx)

        raw_cmd = step.get("command", "")
        cmd = engine.resolve(raw_cmd)

        if not cmd:
            return StepResult.from_error(step_id, "No command specified")

        working_dir = step.get("working_dir", None)
        if working_dir:
            working_dir = engine.resolve(working_dir)

        timeout = step.get("timeout", 60)  # 默认 60s
        capture_output = step.get("capture_output", True)
        shell = step.get("shell", True)  # 默认用 shell（支持管道、重定向）

        env = os.environ.copy()
        raw_env = step.get("env", {})
        if isinstance(raw_env, dict):
            for k, v in raw_env.items():
                env[k] = engine.resolve(str(v))

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                shell=shell,
                cwd=working_dir,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                env=env,
            )
            elapsed = int((time.time() - t0) * 1000)

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            exit_code = result.returncode

            raw_expect = step.get("expect", {})
            if isinstance(raw_expect, dict):
                expected_exit = raw_expect.get("exit_code", 0)
            else:
                expected_exit = 0

            errors = []
            if exit_code != expected_exit:
                errors.append(f"Expected exit code {expected_exit}, got {exit_code}")

            status = "passed" if not errors else "failed"

            # capture from stdout
            capture = {}
            raw_capture = step.get("capture", {})
            if isinstance(raw_capture, dict):
                for key, pattern in raw_capture.items():
                    import re
                    m = re.search(engine.resolve(pattern), stdout)
                    if m:
                        val = m.group(1)
                        try:
                            capture[key] = int(val)
                        except ValueError:
                            try:
                                capture[key] = float(val)
                            except ValueError:
                                capture[key] = val

            # stdout 过长时截断（但完整内容写入 capture）
            response = stdout[:4096] if len(stdout) > 4096 else stdout
            if stderr:
                errors.append(stderr[:512])

            return StepResult(
                step_id=step_id,
                step_type="script",
                status=status,
                send=cmd,
                response=response,
                elapsed_ms=elapsed,
                error="; ".join(errors),
                capture={**capture, "stdout": stdout, "stderr": stderr, "exit_code": exit_code},
            )

        except subprocess.TimeoutExpired:
            return StepResult(
                step_id=step_id,
                step_type="script",
                status="failed",
                send=cmd,
                error=f"Timeout after {timeout}s",
                elapsed_ms=int((time.time() - t0) * 1000),
            )
        except FileNotFoundError as e:
            return StepResult.from_error(step_id, f"Command not found: {e}", step_type="script", send=cmd)
        except Exception as e:
            return StepResult.from_error(step_id, str(e), step_type="script", send=cmd)
