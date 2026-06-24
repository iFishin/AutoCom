"""
PipelineScheduler — AutoCom 流水线调度器（"时钟"）

核心设计：
- 维护程序计数器 (PC)，逐步执行 Steps[]
- 每次 tick 执行一步：条件检查 → handler 分发 → 结果记录 → 控制流跳转
- flow control：if / on_error: retry / goto / abort

用法：
    scheduler = PipelineScheduler(steps, ctx, handlers, action_handler)
    passed = scheduler.run()
"""

from __future__ import annotations

import time
import re
import json
from typing import Any, Optional

from components.Context import Context
from components.steps.base import BaseStepHandler, StepResult
from utils.TemplateEngine import TemplateEngine
from utils.dirs import get_dirs
from components.Logger import get_logger


LOGGABLE_STEP_TYPES = {"serial", "serial_wait", "http", "script", "wait", "action_batch"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class PipelineScheduler:
    """流水线调度器——状态机 + 程序计数器。"""

    def __init__(
        self,
        steps: list[dict],
        ctx: Context,
        handlers: dict[str, BaseStepHandler],
        action_handler: Any = None,  # 旧 ActionHandler（暂保留兼容）
    ):
        # 步骤处理
        self.ordered = self._prepare_steps(steps)
        self.step_map: dict[str, dict] = {
            s["id"]: s for s in self.ordered if s.get("id")
        }
        self.pc = 0          # 程序计数器
        self.pt = 0          # 兼容保留字段
        self._tick_count = 0  # 保护计数器（防止控制流死循环）

        # 运行时状态
        self.ctx = ctx
        self._handlers = handlers
        self._action_handler = action_handler
        self._engine = TemplateEngine(ctx)

        # 预初始化 goto 计数器（确保循环中的步骤能引用到 _goto_count.xxx）
        self._init_goto_counters()

        # 重试/循环计数
        self._retry_count: dict[str, int] = {}
        self._loop_count: dict[str, int] = {}

    # ── 公共入口 ──

    def run(self) -> bool:
        """一次完整的流水线执行。返回 True 表示全部通过。"""
        all_passed = True
        self.pt = time.monotonic()
        self._tick_count = 0

        while self.pc < len(self.ordered):
            self._tick_count += 1
            if self._tick_count > max(len(self.ordered) * 100, 1000):
                all_passed = False
                break

            result = self._tick()

            if result is None:
                break  # abort

            if not result.ok and not result.is_skip:
                all_passed = False

            # 死循环保护由 tick 次数控制，避免长 timeout 步骤误触发

        return all_passed

    def tick(self) -> Optional[StepResult]:
        """单步执行（供外部逐拍调用）。返回 None 表示流水线结束。"""
        if self.pc >= len(self.ordered):
            return None
        return self._tick()

    # ── 内部 TICK ──

    def _tick(self) -> Optional[StepResult]:
        """执行当前 PC 指向的步骤，返回 StepResult。"""
        step = self.ordered[self.pc]
        step_id = step.get("id", f"step_{self.pc}")
        step_type = step.get("type", "serial")

        # ── 0. 手动禁用检查 ──
        if self._is_disabled(step):
            result = StepResult.skipped(step_id)
            self._record(step_id, step_type, result, step=step)
            self.pc += 1
            return result

        # ── 1. if 条件检查 ──
        if self._should_skip(step):
            result = StepResult.skipped(step_id)
            self._record(step_id, step_type, result, step=step)
            self.pc += 1
            return result

        # ── 2. 变量替换 send 和 expect ──
        step = self._resolve_step(step)

        # ── 2.5 元步骤处理：loop / choose / goto ──
        if step_type == "loop":
            result = self._handle_loop(step)
            self._record(step_id, step_type, result, step=step)
            self.pc += 1
            return result

        if step_type == "choose":
            result = self._handle_choose(step)
            self._record(step_id, step_type, result, step=step)
            self.pc += 1
            return result

        if step_type == "goto":
            return self._handle_goto_step(step, step_id)

        # ── 3. 路由到 Handler ──
        handler = self._handlers.get(step_type)
        if handler is None:
            result = StepResult.from_error(
                step_id, f"Unknown step type: '{step_type}'")
        else:
            result = handler.execute(step)

        # ── 4. 记录结果 ──
        self._run_response_actions(step, result)
        self._record(step_id, step_type, result, step=step)

        # ── 5. 执行 success / error actions ──
        if result.ok:
            self._run_actions(step, result, "success_actions")
        else:
            self._run_actions(step, result, "error_actions")

        # ── 6. 控制流 ──
        self._advance_pc(step, result)

        return result

    def _is_disabled(self, step: dict) -> bool:
        """检查 step 是否被手动禁用。"""
        enabled = step.get("enabled", True)
        if enabled is False:
            return True
        if isinstance(enabled, str) and enabled.strip().lower() in (
            "false", "0", "no", "disabled", "disable"
        ):
            return True
        status = str(step.get("status", "")).strip().lower()
        return status in ("disabled", "disable", "false", "0", "off")

    # ── 条件跳过 ──

    def _should_skip(self, step: dict) -> bool:
        """检查 if / unless 条件。"""
        if "if" in step:
            raw = step["if"]
            if not self._engine.evaluate(str(raw)):
                return True
        if "unless" in step:
            raw = step["unless"]
            if self._engine.evaluate(str(raw)):
                return True
        return False

    # ── 变量替换 ──

    def _resolve_step(self, step: dict) -> dict:
        """对 step 中的关键字段做变量替换。"""
        resolved = dict(step)
        for field in ("send", "command", "url", "body", "command"):
            if field in resolved and isinstance(resolved[field], str):
                resolved[field] = self._engine.resolve(resolved[field])
        # expect 列表
        if "expect" in resolved and isinstance(resolved["expect"], list):
            resolved["expect"] = [self._engine.resolve(e) for e in resolved["expect"]]
        return resolved

    # ── 结果记录 ──

    def _record(self, step_id: str, step_type: str, result: StepResult,
                step: Optional[dict] = None):
        self.ctx.record_step(
            step_id=step_id,
            step_type=step_type,
            status=result.status,
            send=result.send,
            response=result.response,
            elapsed_ms=result.elapsed_ms,
            error=result.error,
            capture=result.capture,
        )
        self._write_step_log(step_id, step_type, result, step or {})

    def _write_step_log(self, step_id: str, step_type: str, result: StepResult,
                        step: dict):
        if step_type not in LOGGABLE_STEP_TYPES:
            return

        try:
            log_path = get_dirs().session_dir / self._step_log_filename(step_type, step)
            capture = result.capture or {}
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("=" * 72 + "\n")
                f.write(f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"step_id: {step_id}\n")
                f.write(f"step_type: {step_type}\n")
                f.write(f"status: {result.status}\n")
                f.write(f"elapsed_ms: {result.elapsed_ms}\n")
                if result.send:
                    f.write("\n[send]\n")
                    f.write(f"{result.send}\n")
                if result.response:
                    f.write("\n[response]\n")
                    f.write(f"{result.response}\n")
                if capture:
                    f.write("\n[capture]\n")
                    f.write(json.dumps(capture, ensure_ascii=False, indent=2))
                    f.write("\n")
                if result.error:
                    f.write("\n[error]\n")
                    f.write(f"{result.error}\n")
                f.write("\n")
        except Exception as e:
            get_logger("AutoCom").log_session_warning(
                f"Failed to write step log for {step_type}/{step_id}: {e}")

    @staticmethod
    def _safe_log_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "unnamed"

    def _step_log_filename(self, step_type: str, step: dict) -> str:
        safe_type = self._safe_log_name(step_type or "step")
        if step_type not in ("serial", "serial_wait"):
            return f"{safe_type}.log"

        device_name = step.get("device", "")
        port = ""
        if device_name:
            port = self.ctx.get(f"devices.{device_name}.port", "") or ""
        key = port or device_name or "unknown_port"
        return f"{safe_type}_{self._safe_log_name(key)}.log"

    # ── 元步骤处理：loop ──

    def _handle_loop(self, step: dict) -> StepResult:
        """处理 type: loop 步骤。

        循环执行 inner steps，支持 until 条件和 max_iterations。
        """
        step_id = step.get("id", "")
        inner_steps = step.get("steps", [])
        if not inner_steps:
            return StepResult(step_id=step_id, step_type="loop", status="passed")

        max_iter = _as_int(step.get("max_iterations", 100), 100)
        interval = _as_float(step.get("interval_ms", 0), 0.0) / 1000
        until_expr = step.get("until")

        # 记录循环开始
        self.ctx.set(f"_loop.{step_id}.iteration", 0)

        for iteration in range(max_iter):
            self.ctx.set(f"_loop.{step_id}.iteration", iteration + 1)

            # 执行内层所有步骤
            all_passed = True
            for inner_step in inner_steps:
                # 变量替换
                resolved = self._resolve_step(inner_step)

                # if 条件
                if self._should_skip(resolved):
                    continue

                # 路由到 handler
                inner_type = resolved.get("type", "serial")
                handler = self._handlers.get(inner_type)
                if handler is None:
                    r = StepResult.from_error(resolved.get("id", ""),
                                               f"Unknown type: '{inner_type}'")
                else:
                    r = handler.execute(resolved)

                self._record(
                    step_id=resolved.get("id", f"{step_id}_inner_{iteration}_{inner_type}"),
                    step_type=inner_type, result=r, step=resolved,
                )

                if not r.ok and r.status != "skipped":
                    all_passed = False

            # 检查终止条件
            if until_expr and self._engine.evaluate(until_expr):
                return StepResult(
                    step_id=step_id, step_type="loop",
                    status="passed", send=f"loop {iteration+1} iters",
                    capture={"iterations": iteration + 1},
                )

            if interval > 0:
                import time
                time.sleep(interval)

        return StepResult(
            step_id=step_id, step_type="loop",
            status="passed", send=f"loop {max_iter} iters (max)",
            capture={"iterations": max_iter},
        )

    # ── 元步骤处理：choose ──

    def _handle_choose(self, step: dict) -> StepResult:
        """处理 type: choose 步骤。

        按顺序评估分支的 if 条件，执行第一个匹配分支的内层 steps。
        有 default 分支作为兜底。
        """
        step_id = step.get("id", "")
        branches = step.get("branches", [])

        default_branch = None
        executed_branch = None

        for branch in branches:
            if branch.get("default"):
                default_branch = branch
                continue

            raw_if = branch.get("if")
            if raw_if is None or self._engine.evaluate(str(raw_if)):
                executed_branch = branch
                break

        if executed_branch is None:
            executed_branch = default_branch

        if executed_branch is None:
            return StepResult(
                step_id=step_id, step_type="choose",
                status="skipped", send="no matching branch",
            )

        # 执行选中分支的内层步骤
        inner_steps = executed_branch.get("steps", [])
        branch_id = executed_branch.get("id", "default")
        all_passed = True

        for inner_step in inner_steps:
            resolved = self._resolve_step(inner_step)
            if self._should_skip(resolved):
                continue

            inner_type = resolved.get("type", "serial")
            handler = self._handlers.get(inner_type)
            if handler is None:
                r = StepResult.from_error(resolved.get("id", ""),
                                           f"Unknown type: '{inner_type}'")
            else:
                r = handler.execute(resolved)

            self._record(
                step_id=resolved.get("id", f"{step_id}_{branch_id}"),
                step_type=inner_type, result=r, step=resolved,
            )

            if not r.ok and r.status != "skipped":
                all_passed = False

        return StepResult(
            step_id=step_id, step_type="choose",
            status="passed" if all_passed else "failed",
            send=f"branch: {branch_id}",
            capture={"branch": branch_id},
        )

    # ── 元步骤处理：goto（顶层跳转循环） ──

    def _handle_goto_step(self, step: dict, step_id: str) -> StepResult:
        """处理 type: goto 步骤。

        无条件或有条件跳转到指定 step，实现多步骤循环。

        用法:
          - id: loop_back
            type: goto
            target: measure
            max_iterations: 5           # 最多循环 5 次

        或带条件:
          - id: loop_back
            type: goto
            target: measure
            if: "{{ steps.some_step.status }} != passed"
        """
        target = step.get("target", "")
        max_n = _as_int(step.get("max_iterations", 0), 0)

        # 自动递增计数器
        count = self.ctx.get(f"_goto_count.{step_id}", 0)
        self.ctx.set(f"_goto_count.{step_id}", count + 1)

        # max_iterations 限制
        if max_n > 0 and count >= max_n:
            self.pc += 1
            return StepResult(
                step_id=step_id, step_type="goto",
                status="skipped", send=f"max {max_n} reached",
            )

        # if 条件（条件为 false 则跳过跳转，继续执行后续步骤）
        if self._should_skip(step):
            self.pc += 1
            return StepResult(
                step_id=step_id, step_type="goto",
                status="skipped", send="condition not met",
            )

        # 执行跳转
        idx = self._find_index_by_id(target)
        if idx is not None:
            self.pc = idx
            return StepResult(
                step_id=step_id, step_type="goto",
                status="passed",
                send=f"-> {target} (#{count + 1})",
                capture={"goto_count": count + 1, "target": target},
            )

        # 目标不存在
        self.pc += 1
        return StepResult(
            step_id=step_id, step_type="goto",
            status="error", error=f"target '{target}' not found",
        )

    # ── Actions 执行 ──

    def _run_response_actions(self, step: dict, result: StepResult):
        """根据步骤响应内容触发 response_actions。"""
        rules = step.get("response_actions", [])
        if not rules or not self._action_handler:
            return

        triggered = []
        response = result.response or ""
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue

            matched = False
            pattern = None
            match_type = "when"
            if "when" in rule:
                pattern = self._engine.resolve(str(rule.get("when", "")))
                matched = pattern in response
            elif "matches" in rule:
                pattern = self._engine.resolve(str(rule.get("matches", "")))
                match_type = "matches"
                try:
                    matched = bool(re.search(pattern, response))
                except re.error as e:
                    triggered.append({
                        "rule": idx,
                        "type": match_type,
                        "pattern": pattern,
                        "status": "error",
                        "detail": f"invalid regex: {e}",
                    })
                    continue

            if not matched:
                continue

            actions = rule.get("actions", [])
            context = {
                "device": self.ctx.get(f"_runtime.devices.{step.get('device', '')}"),
                "device_name": step.get("device", ""),
                "cmd_str": result.send,
                "expected_responses": step.get("expect", step.get("expected_responses", [])),
                "priority": step.get("priority", 0),
                "completion_rules": step.get("completion_rules"),
                "_action_results": [],
            }
            ok = self._action_handler.handle_actions(
                {"actions": actions}, response, "actions", context)
            triggered.append({
                "rule": idx,
                "type": match_type,
                "pattern": pattern,
                "status": "passed" if ok else "failed",
                "actions": context.get("_action_results", []),
            })

        if triggered:
            capture = dict(result.capture or {})
            capture["response_actions"] = triggered
            result.capture = capture

    def _run_actions(self, step: dict, result: StepResult, action_key: str):
        """执行 success_actions 或 error_actions。"""
        actions = step.get(action_key, [])
        if not actions:
            return

        # 使用 ActionHandler 或内置简化处理器
        if self._action_handler:
            # 构建一个兼容的 context dict
            context = {
                "device_name": step.get("device", ""),
                "cmd_str": result.send,
                "expected_responses": step.get("expect", step.get("expected_responses", [])),
            }
            self._action_handler.handle_actions(
                {"temp_actions": actions}, result.response,
                "temp_actions", context)

    # ── 程序计数器 ──

    def _advance_pc(self, step: dict, result: StepResult):
        """根据执行结果和 flow control 配置移动 PC。"""
        if result.ok:
            cmd = step.get("on_success", "continue")
        else:
            cmd = step.get("on_error", "continue")

        if cmd is None or cmd == "continue":
            self.pc += 1
        elif cmd == "skip":
            self.pc += 1
        elif cmd == "abort":
            self.pc = len(self.ordered)  # 结束流水线
        elif cmd.startswith("retry"):
            self._handle_retry(step, result, cmd)
        elif cmd.startswith("goto"):
            self._handle_goto(cmd)
        elif cmd.startswith("restart"):
            self.pc = 0  # 从第一步重新开始
        else:
            self.pc += 1  # fallback

    def _handle_retry(self, step: dict, result: StepResult, cmd: str):
        """处理 retry(N) 逻辑。"""
        m = re.match(r"retry\s*\(\s*(\d+)\s*\)", cmd)
        if not m:
            self.pc += 1
            return

        max_retries = int(m.group(1))
        step_id = step.get("id", "")
        current = self._retry_count.get(step_id, 0) + 1
        self._retry_count[step_id] = current

        if current <= max_retries:
            # PC 不动，重新执行本步
            self.pt = time.monotonic()  # 刷新保护计时
            return

        # 重试耗尽，继续下一步
        self.pc += 1

    def _handle_goto(self, cmd: str):
        """处理 goto(id) 逻辑。"""
        m = re.match(r"goto\s*\(\s*(.+)\s*\)", cmd)
        if not m:
            self.pc += 1
            return

        target_id = m.group(1).strip().strip("'\"")
        idx = self._find_index_by_id(target_id)
        if idx is not None:
            self.pc = idx
        else:
            self.pc += 1  # 找不到目标，继续下一步

    def _find_index_by_id(self, step_id: str) -> Optional[int]:
        """根据 step id 查找其在 ordered 列表中的索引。"""
        for i, s in enumerate(self.ordered):
            if s.get("id") == step_id:
                return i
        return None

    def retry_step(self, step_id: str):
        """外部触发的重试（从 action 中调用）。"""
        idx = self._find_index_by_id(step_id)
        if idx is not None:
            self.pc = idx

    # ── 步骤预处理 ──

    @staticmethod
    def _prepare_steps(steps: list[dict]) -> list[dict]:
        """对步骤排序、补全 id、类型、order 等默认值。"""
        if not steps:
            return []

        for i, s in enumerate(steps):
            # id 自动生成
            if "id" not in s or not s.get("id"):
                s["id"] = f"step_{i}"
            s["id"] = str(s["id"])

            # order 自动递增（缺省由上往下排）
            if "order" not in s:
                s["order"] = i + 1

            # type 默认 serial
            if "type" not in s:
                s["type"] = "serial"

            # expect 单字符串 → 列表
            if "expect" in s and isinstance(s["expect"], str):
                s["expect"] = [s["expect"]]

            # expect_responses 旧字段兼容
            if "expected_responses" in s and "expect" not in s:
                s["expect"] = (
                    [s["expected_responses"]]
                    if isinstance(s["expected_responses"], str)
                    else s["expected_responses"]
                )

        # 按 order 排序
        ordered = sorted(steps, key=lambda s: s.get("order", 999))
        return ordered

    def _init_goto_counters(self):
        """预初始化所有 type: goto 步骤的计数器，确保循环中引用 _goto_count.xxx 总是有值。"""
        for step in self.ordered:
            if step.get("type") == "goto":
                step_id = step.get("id", "")
                if step_id:
                    self.ctx.set(f"_goto_count.{step_id}", 1)

    # ── 兼容旧 Commands → Steps 转换 ──

    @classmethod
    def from_old_commands(cls, commands: list[dict],
                          ctx: Context, handlers: dict,
                          action_handler: Any = None) -> "PipelineScheduler":
        """将旧格式 Commands[] 转为 Steps[] 并创建调度器。"""
        steps = cls._convert_commands(commands)
        return cls(steps, ctx, handlers, action_handler)

    @staticmethod
    def _convert_commands(commands: list[dict]) -> list[dict]:
        """旧 Commands[] → 新 Steps[] 自动转换。"""
        steps = []
        for cmd in commands:
            step = {"type": "serial", **cmd}
            # 字段映射
            if "command" in step and "send" not in step:
                step["send"] = step.pop("command")
            if "expected_responses" in step and "expect" not in step:
                step["expect"] = step.pop("expected_responses")
            if "variables" in step and "capture" not in step:
                step["capture"] = step.pop("variables")
            if "hex_mode" in step:
                step.pop("hex_mode")  # 旧字段保留在 type: serial 专属处理中
            if "priority" in step:
                step.pop("priority")
            if "completion_rules" in step:
                step.pop("completion_rules")
            if "concurrent_strategy" in step:
                step.pop("concurrent_strategy")
            steps.append(step)
        return steps
