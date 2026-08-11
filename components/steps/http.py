"""
HttpStepHandler — 执行 HTTP 请求的 Step Handler。

从 CustomActionHandler.handle_http_request() 抽取。
"""

from __future__ import annotations

import time
from typing import Any

from components.steps.base import BaseStepHandler, StepResult
from utils.TemplateEngine import TemplateEngine


class HttpStepHandler(BaseStepHandler):
    """处理 type: http 的步骤。"""

    def execute(self, step: dict) -> StepResult:
        step_id = step.get("id", "")
        engine = TemplateEngine(self.ctx)

        # ignore_error: 为 true 时无论成功/失败都判定为 passed
        ignore_error = step.get("ignore_error", False)

        try:
            import requests as req
        except ImportError:
            return StepResult.from_error(
                step_id, "requests library not installed. Run: pip install requests"
            )

        # 解析参数
        raw_url = step.get("url", "")
        method = step.get("method", "GET").upper()
        raw_headers = step.get("headers", {})
        raw_body = step.get("body", {})

        url = engine.resolve(raw_url)
        headers = (
            engine.resolve_dict(raw_headers) if isinstance(raw_headers, dict) else {}
        )
        timeout = step.get("timeout", 10)

        t0 = time.time()
        try:
            if method == "GET":
                resp = req.get(url, headers=headers, timeout=timeout)
            elif method == "POST":
                body = (
                    engine.resolve_dict(raw_body)
                    if isinstance(raw_body, dict)
                    else raw_body
                )
                content_type = step.get("content_type", "json")
                if content_type == "json":
                    resp = req.post(url, headers=headers, json=body, timeout=timeout)
                else:
                    resp = req.post(url, headers=headers, data=body, timeout=timeout)
            elif method == "PUT":
                body = (
                    engine.resolve_dict(raw_body)
                    if isinstance(raw_body, dict)
                    else raw_body
                )
                resp = req.put(url, headers=headers, json=body, timeout=timeout)
            elif method == "DELETE":
                resp = req.delete(url, headers=headers, timeout=timeout)
            else:
                return StepResult.from_error(
                    step_id, f"Unsupported HTTP method: {method}"
                )

            elapsed = int((time.time() - t0) * 1000)

            # 检查 expect
            raw_expect = step.get("expect", {})
            if isinstance(raw_expect, dict):
                expected_status = raw_expect.get("status_code", None)
                body_match = raw_expect.get("body_match", None)
            else:
                expected_status = None
                body_match = None

            errors = []
            if expected_status is not None and resp.status_code != int(expected_status):
                errors.append(
                    f"Expected status {expected_status}, got {resp.status_code}"
                )
            if body_match:
                import re

                if not re.search(str(body_match), resp.text):
                    errors.append(f"Body does not match pattern: {body_match}")

            status = "passed" if not errors else "failed"

            # ignore_error: 强制判定为 passed，保留错误信息便于排查
            if ignore_error and status != "passed":
                status = "passed"

            # capture from response
            capture = {}
            raw_capture = step.get("capture", {})
            if isinstance(raw_capture, dict):
                for key, pattern in raw_capture.items():
                    import re

                    m = re.search(engine.resolve(pattern), resp.text)
                    if m:
                        capture[key] = m.group(1)

            return StepResult(
                step_id=step_id,
                step_type="http",
                status=status,
                send=f"{method} {url}",
                response=resp.text[:4096],  # 截断防止超大
                elapsed_ms=elapsed,
                error="; ".join(errors),
                capture=capture,
            )

        except Exception as e:
            # ignore_error: 异常也判定为 passed，保留 error 信息
            if ignore_error:
                return StepResult(
                    step_id=step_id,
                    step_type="http",
                    status="passed",
                    send=f"{method} {url}",
                    error=str(e),
                )
            return StepResult.from_error(
                step_id, str(e), step_type="http", send=f"{method} {url}"
            )
