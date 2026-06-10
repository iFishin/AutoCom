#!/usr/bin/env python3
"""
AutoCom MCP Server - FastMCP 重构实现

使用 FastMCP 暴露 AutoCom 的串口操作能力，支持 stdio、SSE、Streamable HTTP 三种运行模式。
保留原有工具实现（扫描串口、执行指令、批量执行、加载执行配置文件、监听串口），并将它们注册为 FastMCP 工具。
"""

from __future__ import annotations

import asyncio
import json
import time
import inspect
import contextlib
import io
from collections import deque
import serial
import sys
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from typing import Any, Optional, List

try:
    from fastmcp import FastMCP, Context
    from fastmcp.server.dependencies import get_context
    _FASTMCP_AVAILABLE = True
except Exception:  # pragma: no cover
    FastMCP = None
    Context = Any
    get_context = None
    _FASTMCP_AVAILABLE = False

from components.Logger import AutoComLogger, get_logger
logger: AutoComLogger = get_logger("AutoCom.MCP")


def _is_graceful_shutdown_exception(exc: BaseException) -> bool:
    """判断是否属于可静默处理的退出类异常。"""
    graceful_types = (KeyboardInterrupt, asyncio.CancelledError, BrokenPipeError, EOFError)
    if isinstance(exc, graceful_types):
        return True

    # Python 3.11+：ExceptionGroup 可能包装取消/中断异常
    with contextlib.suppress(Exception):
        if isinstance(exc, BaseExceptionGroup):  # type: ignore[name-defined]
            return all(_is_graceful_shutdown_exception(e) for e in exc.exceptions)

    return False


def _run_coroutine_with_graceful_shutdown(coro, on_interrupt=None, suppress_stderr_on_graceful: bool = False):
    """运行协程并在 Ctrl+C/取消时安静退出，避免向终端打印大量堆栈。"""

    def _loop_exception_handler(loop, context):
        exc = context.get("exception")
        if isinstance(exc, BaseException) and _is_graceful_shutdown_exception(exc):
            return
        loop.default_exception_handler(context)

    stderr_buffer = io.StringIO() if suppress_stderr_on_graceful else None

    def _run_impl():
        if hasattr(asyncio, "Runner"):
            with asyncio.Runner() as runner:
                loop = runner.get_loop()
                loop.set_exception_handler(_loop_exception_handler)
                return runner.run(coro)
        return asyncio.run(coro)

    try:
        if stderr_buffer is not None:
            with contextlib.redirect_stderr(stderr_buffer):
                return _run_impl()
        return _run_impl()
    except BaseException as e:
        if _is_graceful_shutdown_exception(e):
            if callable(on_interrupt):
                on_interrupt()
            return None

        if stderr_buffer is not None:
            buffered = stderr_buffer.getvalue()
            if buffered:
                with contextlib.suppress(Exception):
                    sys.stderr.write(buffered)
                    sys.stderr.flush()
        raise
    finally:
        if stderr_buffer is not None:
            stderr_buffer.close()


class AutoComMCPServer:
    """基于 FastMCP 的 MCP Server，工具以装饰器方式注册到 `self.mcp`。"""

    def __init__(self, server_name: str = "autocom", auth_key: Optional[str] = None):
        if not _FASTMCP_AVAILABLE:
            raise RuntimeError("fastmcp 未安装。请运行: pip install fastmcp")

        self.auth_key = auth_key
        if FastMCP is None:
            raise RuntimeError("FastMCP 类不可用，可能是 fastmcp 版本不兼容。请升级 fastmcp 或检查其文档。")
        self.mcp = FastMCP()
        self._register_tools()

    def _register_tools(self) -> None:
        mcp = self.mcp

        @mcp.tool()
        async def list_devices() -> dict:
            """列出当前可用的串口设备及其信息"""
            logger.log_info("MCP: list_devices called")
            return await AutoComMCPServer._list_devices()

        @mcp.tool()
        async def execute_command(
            port: str,
            command: str,
            baud_rate: int = 115200,
            timeout: float = 5.0,
            line_ending: str = "0d0a",
            hex_mode: bool = False,
            device_name: Optional[str] = None,
            expected_responses: Optional[List[str]] = None,
            completion_rules: Optional[dict] = None,
            priority: int = 0,
        ) -> dict:
            """向指定串口设备发送单条指令并返回响应"""
            logger.log_info(f"MCP: execute_command on {port}")
            return await AutoComMCPServer._execute_command(
                port=port,
                command=command,
                baud_rate=baud_rate,
                timeout=timeout,
                line_ending=line_ending,
                hex_mode=hex_mode,
                device_name=device_name,
                expected_responses=expected_responses,
                completion_rules=completion_rules,
                priority=priority,
            )

        @mcp.tool()
        async def execute_commands(
            port: str,
            commands: List[str],
            baud_rate: int = 115200,
            parallel: bool = False,
            timeout: float = 5.0,
            device_name: Optional[str] = None,
            expected_responses: Optional[List[str]] = None,
            completion_rules: Optional[dict] = None,
            priority: int = 0,
        ) -> dict:
            """批量执行多条指令（支持串行/并行），返回所有结果"""
            logger.log_info(f"MCP: execute_commands on {port} count={len(commands)} parallel={parallel}")
            return await AutoComMCPServer._execute_commands(
                port=port,
                commands=commands,
                baud_rate=baud_rate,
                parallel=parallel,
                timeout=timeout,
                device_name=device_name,
                expected_responses=expected_responses,
                completion_rules=completion_rules,
                priority=priority,
            )

        @mcp.tool()
        async def load_dict(file_path: str, config_path: Optional[str] = None) -> dict:
            """加载并解析 AutoCom 执行配置文件（JSON/YAML），返回设备与指令配置"""
            logger.log_info(f"MCP: load_dict {file_path}")
            return await AutoComMCPServer._load_dict(file_path=file_path, config_path=config_path)

        @mcp.tool()
        async def validate_dict(file_path: str, config_path: Optional[str] = None) -> dict:
            """校验 AutoCom 执行配置文件（JSON/YAML），返回错误与告警"""
            logger.log_info(f"MCP: validate_dict {file_path}")
            return await AutoComMCPServer._validate_dict(file_path=file_path, config_path=config_path)

        @mcp.tool()
        async def monitor_port(port: str, baud_rate: int = 115200, duration: float = 10.0) -> dict:
            """监听串口设备输出（持续读取），返回一段时间内的输出内容"""
            logger.log_info(f"MCP: monitor_port {port} duration={duration}")
            return await AutoComMCPServer._monitor_port(port=port, baud_rate=baud_rate, duration=duration)

        @mcp.tool()
        async def monitor_port_stream(
            port: str,
            baud_rate: int = 115200,
            duration: float = 30.0,
            heartbeat_interval: float = 0.3,
        ) -> dict:
            """实时监听串口并通过 MCP progress 通知持续推送数据。

            注意：FastMCP 对工具返回的 async generator 会先整体物化，因此不能用于真正逐条实时回传。
            本方法改为在工具执行过程中通过 progress message 持续发送数据，最后返回一次汇总。
            """
            logger.log_info(
                f"MCP: monitor_port_stream {port} duration={duration} heartbeat={heartbeat_interval}"
            )

            progress_token = None
            ctx: Optional[Any] = None
            try:
                ctx = get_context() if callable(get_context) else None
                if ctx and ctx.request_context and ctx.request_context.meta:
                    progress_token = ctx.request_context.meta.progressToken
            except Exception:
                progress_token = None

            progress_enabled = progress_token is not None
            if duration <= 0 and not progress_enabled:
                return {
                    "success": False,
                    "port": port,
                    "error": "当前客户端未启用 progressToken，duration<=0 会导致无返回。请传入 duration>0，或使用支持 progress callback 的 MCP 客户端。",
                }

            ser = None
            outputs = deque(maxlen=200)
            chunk_count = 0
            byte_count = 0
            start_time = time.time()
            heartbeat_interval = max(heartbeat_interval, 0.05)
            last_heartbeat_ts = 0.0

            async def _emit(event: str, data_text: str | None = None) -> None:
                if not progress_enabled:
                    return
                current_ctx = ctx
                if current_ctx is None:
                    return
                payload = {
                    "event": event,
                    "port": port,
                    "timestamp_ms": round((time.time() - start_time) * 1000, 1),
                    "chunk_count": chunk_count,
                    "byte_count": byte_count,
                }
                if data_text is not None:
                    payload["data"] = data_text
                try:
                    await current_ctx.report_progress(chunk_count, None, json.dumps(payload, ensure_ascii=False))
                except Exception:
                    pass

            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0,
                )
            except Exception as e:
                return {"success": False, "port": port, "error": str(e)}

            try:
                await _emit("connected")

                end_at = None if duration <= 0 else (start_time + duration)
                while True:
                    if end_at is not None and time.time() >= end_at:
                        break

                    try:
                        avail = getattr(ser, "in_waiting", None)
                        if avail is not None:
                            data = ser.read(avail) if avail > 0 else b""
                        else:
                            data = ser.read_all()
                    except Exception:
                        try:
                            data = ser.read_all()
                        except Exception:
                            data = b""

                    if data:
                        byte_count += len(data)
                        chunk_count += 1
                        try:
                            text = data.decode("utf-8", errors="replace")
                        except Exception:
                            text = data.hex(" ")

                        record = {
                            "timestamp_ms": round((time.time() - start_time) * 1000, 1),
                            "data": text,
                        }
                        outputs.append(record)
                        await _emit("data", text)
                        last_heartbeat_ts = time.time()
                    else:
                        now = time.time()
                        if now - last_heartbeat_ts >= heartbeat_interval:
                            await _emit("heartbeat")
                            last_heartbeat_ts = now

                    await asyncio.sleep(0.03)

                await _emit("completed")
                return {
                    "success": True,
                    "port": port,
                    "duration_seconds": round(time.time() - start_time, 3),
                    "progress_enabled": progress_enabled,
                    "total_chunks": chunk_count,
                    "total_bytes": byte_count,
                    "tail_chunks": list(outputs),
                }
            except (KeyboardInterrupt, asyncio.CancelledError):
                await _emit("cancelled")
                return {
                    "success": True,
                    "port": port,
                    "cancelled": True,
                    "duration_seconds": round(time.time() - start_time, 3),
                    "progress_enabled": progress_enabled,
                    "total_chunks": chunk_count,
                    "total_bytes": byte_count,
                    "tail_chunks": list(outputs),
                }
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

    # ------------------------- 工具实现（复用原有实现） -------------------------
    @staticmethod
    async def _list_devices() -> dict:
        import serial.tools.list_ports

        devices = []
        for p in serial.tools.list_ports.comports():
            devices.append({
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "vid": getattr(p, "vid", None),
                "pid": getattr(p, "pid", None),
                "serial_number": getattr(p, "serial_number", None),
                "manufacturer": getattr(p, "manufacturer", None),
            })
        return {"total": len(devices), "devices": devices}

    @staticmethod
    async def _execute_command(
        port: str,
        command: str,
        baud_rate: int = 115200,
        timeout: float = 5.0,
        line_ending: str = "0d0a",
        hex_mode: bool = False,
        device_name: Optional[str] = None,
        expected_responses: Optional[List[str]] = None,
        completion_rules: Optional[dict] = None,
        priority: int = 0,
    ) -> dict:

        start_time = time.time()
        response_data = ""
        expected_responses = expected_responses or []
        completion_rules = completion_rules or {}
        matched: List[str] = []
        finish_reason = "timeout"

        idle_timeout = float(completion_rules.get("idle_timeout", min(timeout / 3, 2.0)))
        settle_after_terminal = float(completion_rules.get("settle_after_terminal", 0.05))
        expected_required = bool(completion_rules.get("expected_required", False))
        terminal_patterns = completion_rules.get("terminal_patterns", ["OK", "ERROR"])
        complete_patterns = completion_rules.get("complete_patterns", [])

        ser = None
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
            )

            if isinstance(line_ending, str):
                try:
                    le_bytes = bytes.fromhex(line_ending.replace(" ", ""))
                except Exception:
                    le_bytes = line_ending.encode()
            else:
                le_bytes = line_ending

            if hex_mode:
                cmd_bytes = bytes.fromhex(command.replace(" ", ""))
            else:
                cmd_bytes = command.encode() + le_bytes

            ser.write(cmd_bytes)

            last_data_time = time.time()
            terminal_seen_time = None
            chunks: List[str] = []

            while (time.time() - start_time) < timeout:
                data = ser.read_all()
                if data:
                    last_data_time = time.time()
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except Exception:
                        text = data.hex(" ")
                    chunks.append(text)
                    response_data = "".join(chunks)

                    matched = AutoComMCPServer._match_expected_responses(
                        response_data, expected_responses
                    )
                    should_finish, finish_reason, terminal_seen_time = AutoComMCPServer._should_finish_response(
                        response_text=response_data,
                        expected_responses=expected_responses,
                        completion_rules=completion_rules,
                        terminal_patterns=terminal_patterns,
                        complete_patterns=complete_patterns,
                        expected_required=expected_required,
                        terminal_seen_time=terminal_seen_time,
                        now=time.time(),
                        settle_after_terminal=settle_after_terminal,
                    )
                    if should_finish:
                        break

                if response_data and (time.time() - last_data_time) >= idle_timeout:
                    finish_reason = "idle-timeout"
                    break

                await asyncio.sleep(0.03)

            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "success": True,
                "port": port,
                "command": command,
                "response": response_data.strip(),
                "matched": matched,
                "priority": priority,
                "finish_reason": finish_reason,
                "elapsed_ms": round(elapsed_ms, 2),
            }
        except serial.SerialException as e:
            return {
                "success": False,
                "port": port,
                "command": command,
                "error": f"串口错误: {e}",
                "elapsed_ms": round((time.time() - start_time) * 1000, 2),
            }
        except Exception as e:
            return {
                "success": False,
                "port": port,
                "command": command,
                "error": str(e),
                "elapsed_ms": round((time.time() - start_time) * 1000, 2),
            }
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    @staticmethod
    async def _execute_commands(
        port: str,
        commands: List[str],
        baud_rate: int = 115200,
        parallel: bool = False,
        timeout: float = 5.0,
        device_name: Optional[str] = None,
        expected_responses: Optional[List[str]] = None,
        completion_rules: Optional[dict] = None,
        priority: int = 0,
    ) -> dict:
        results = []
        if parallel:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(commands), 10)) as executor:
                fut_to_cmd = {
                    executor.submit(
                        AutoComMCPServer._execute_command_sync,
                        port=port,
                        command=cmd,
                        baud_rate=baud_rate,
                        timeout=timeout,
                        expected_responses=expected_responses,
                        completion_rules=completion_rules,
                        priority=priority,
                    ): cmd
                    for cmd in commands
                }
                for future in concurrent.futures.as_completed(fut_to_cmd):
                    cmd = fut_to_cmd[future]
                    try:
                        results.append(future.result())
                    except Exception as e:
                        results.append({"success": False, "command": cmd, "error": str(e)})
        else:
            for cmd in commands:
                result = await AutoComMCPServer._execute_command(
                    port=port,
                    command=cmd,
                    baud_rate=baud_rate,
                    timeout=timeout,
                    device_name=device_name,
                    expected_responses=expected_responses,
                    completion_rules=completion_rules,
                    priority=priority,
                )
                results.append(result)

        return {
            "port": port,
            "total": len(commands),
            "parallel": parallel,
            "success_count": sum(1 for r in results if r.get("success")),
            "fail_count": sum(1 for r in results if not r.get("success")),
            "results": results,
        }

    @staticmethod
    def _execute_command_sync(
        port: str,
        command: str,
        baud_rate: int = 115200,
        timeout: float = 5.0,
        expected_responses: Optional[List[str]] = None,
        completion_rules: Optional[dict] = None,
        priority: int = 0,
    ) -> dict:
        import asyncio

        return asyncio.run(
            AutoComMCPServer._execute_command(
                port=port,
                command=command,
                baud_rate=baud_rate,
                timeout=timeout,
                expected_responses=expected_responses,
                completion_rules=completion_rules,
                priority=priority,
            )
        )

    @staticmethod
    def _match_patterns(response_text: str, patterns: Optional[List[str]]) -> bool:
        if not patterns:
            return False
        return any(p in response_text for p in patterns)

    @staticmethod
    def _match_expected_responses(response_text: str, expected_responses: Optional[List[str]]) -> List[str]:
        if not expected_responses:
            return []
        return [p for p in expected_responses if p in response_text]

    @staticmethod
    def _should_finish_response(
        response_text: str,
        expected_responses: Optional[List[str]],
        completion_rules: dict,
        terminal_patterns: List[str],
        complete_patterns: List[str],
        expected_required: bool,
        terminal_seen_time: Optional[float],
        now: float,
        settle_after_terminal: float,
    ) -> tuple[bool, str, Optional[float]]:
        if not response_text:
            return False, "waiting", terminal_seen_time

        matched_expected = AutoComMCPServer._match_expected_responses(
            response_text, expected_responses
        )
        if matched_expected:
            return True, "expected-matched", terminal_seen_time

        if AutoComMCPServer._match_patterns(response_text, complete_patterns):
            return True, "custom-pattern-matched", terminal_seen_time

        if AutoComMCPServer._match_patterns(response_text, terminal_patterns):
            if expected_required:
                return False, "terminal-seen-awaiting-expected", terminal_seen_time
            if terminal_seen_time is None:
                terminal_seen_time = now
            if (now - terminal_seen_time) >= settle_after_terminal:
                return True, "terminal-pattern-matched", terminal_seen_time

        return False, "waiting", terminal_seen_time

    @staticmethod
    async def _load_dict(file_path: str, config_path: Optional[str] = None) -> dict:
        import os
        import json

        path = file_path
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)

        if not os.path.exists(path):
            return {"success": False, "error": f"文件不存在: {path}"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

            dict_data = None
            lower = path.lower()
            if lower.endswith(".json"):
                try:
                    dict_data = json.loads(text)
                except json.JSONDecodeError as e:
                    return {"success": False, "error": f"JSON 格式错误: {e}"}
            elif lower.endswith((".yaml", ".yml")):
                try:
                    import yaml

                    dict_data = yaml.safe_load(text)
                except ImportError:
                    return {"success": False, "error": "缺少 pyyaml 依赖: pip install pyyaml"}
                except Exception as e:
                    return {"success": False, "error": f"YAML 格式错误: {e}"}
            else:
                try:
                    dict_data = json.loads(text)
                except json.JSONDecodeError:
                    try:
                        import yaml

                        dict_data = yaml.safe_load(text)
                    except ImportError:
                        return {"success": False, "error": "文件不是有效 JSON，且未安装 pyyaml。请安装 pyyaml 或提供 JSON 文件。"}
                    except Exception as e:
                        return {"success": False, "error": f"YAML 格式错误: {e}"}
        except Exception as e:
            return {"success": False, "error": f"文件读取失败: {e}"}

        config = None
        if config_path:
            config_p = config_path
            if not os.path.isabs(config_p):
                config_p = os.path.join(os.getcwd(), config_p)
            if os.path.exists(config_p):
                try:
                    with open(config_p, "r", encoding="utf-8") as f:
                        config_text = f.read()
                    if config_p.lower().endswith(".json"):
                        try:
                            config = json.loads(config_text)
                        except Exception:
                            config = None
                    else:
                        try:
                            import yaml

                            config = yaml.safe_load(config_text)
                        except Exception:
                            config = None
                except Exception:
                    config = None

        return {"success": True, "file_path": path, "config_merged": config is not None, "summary": AutoComMCPServer._summarize_dict(dict_data), "data": dict_data}

    @staticmethod
    async def _validate_dict(file_path: str, config_path: Optional[str] = None) -> dict:
        loaded = await AutoComMCPServer._load_dict(file_path=file_path, config_path=config_path)
        if not loaded.get("success"):
            return loaded

        dict_data = loaded.get("data") or {}
        issues: List[dict] = []
        warnings: List[dict] = []

        if not isinstance(dict_data, dict):
            issues.append({"path": "$", "message": "配置根节点必须是对象(dict)"})
        else:
            devices = dict_data.get("Devices") or dict_data.get("devices") or []
            commands = dict_data.get("Commands") or dict_data.get("commands") or []

            if not devices:
                issues.append({"path": "Devices", "message": "Devices 不能为空"})
            if not commands:
                issues.append({"path": "Commands", "message": "Commands 不能为空"})

            enabled_names = set()
            if isinstance(devices, list):
                for idx, dev in enumerate(devices):
                    if not isinstance(dev, dict):
                        issues.append({"path": f"Devices[{idx}]", "message": "设备项必须是对象"})
                        continue
                    name = dev.get("name")
                    if not name:
                        issues.append({"path": f"Devices[{idx}].name", "message": "设备必须配置 name"})
                    if dev.get("status", "enabled") != "disabled" and name:
                        enabled_names.add(name)

            if isinstance(commands, list):
                for idx, cmd in enumerate(commands):
                    if not isinstance(cmd, dict):
                        issues.append({"path": f"Commands[{idx}]", "message": "命令项必须是对象"})
                        continue
                    dev_name = cmd.get("device")
                    if not dev_name:
                        issues.append({"path": f"Commands[{idx}].device", "message": "命令必须指定 device"})
                    elif enabled_names and dev_name not in enabled_names:
                        warnings.append({
                            "path": f"Commands[{idx}].device",
                            "message": f"命令引用的设备 '{dev_name}' 未在已启用 Devices 中找到",
                        })

                    timeout = cmd.get("timeout")
                    if timeout is not None:
                        try:
                            timeout_val = float(timeout)
                            if timeout_val <= 0:
                                issues.append({"path": f"Commands[{idx}].timeout", "message": "timeout 必须大于 0"})
                        except Exception:
                            issues.append({"path": f"Commands[{idx}].timeout", "message": "timeout 必须是数值"})

        return {
            "success": len(issues) == 0,
            "file_path": loaded.get("file_path"),
            "summary": loaded.get("summary"),
            "issue_count": len(issues),
            "warning_count": len(warnings),
            "issues": issues,
            "warnings": warnings,
        }

    @staticmethod
    def _summarize_dict(dict_data: dict) -> dict:
        devices = dict_data.get("devices", []) if isinstance(dict_data, dict) else []
        commands = dict_data.get("commands", []) if isinstance(dict_data, dict) else []
        constants = dict_data.get("constants", {}) if isinstance(dict_data, dict) else {}
        config_for_device = dict_data.get("config_for_device", {}) if isinstance(dict_data, dict) else {}
        config_for_commands = dict_data.get("config_for_commands", {}) if isinstance(dict_data, dict) else {}

        return {
            "device_count": len(devices),
            "device_names": [d.get("name", d.get("port", "unknown")) for d in devices],
            "command_count": len(commands),
            "command_names": [c.get("name", c.get("command", f"cmd_{i}"))[:50] for i, c in enumerate(commands)],
            "has_constants": len(constants) > 0,
            "constant_keys": list(constants.keys()),
            "has_config_for_device": len(config_for_device) > 0,
            "has_config_for_commands": len(config_for_commands) > 0,
        }

    @staticmethod
    async def _monitor_port(port: str, baud_rate: int = 115200, duration: float = 10.0) -> dict:

        outputs = []
        start_time = time.time()
        ser = None
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.5
            )
            while time.time() - start_time < duration:
                data = ser.read_all()
                if data:
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except Exception:
                        text = data.hex(" ")
                    outputs.append({"timestamp": round((time.time() - start_time) * 1000, 1), "data": text})
                await asyncio.sleep(0.05)
            return {
                "success": True,
                "port": port,
                "duration_seconds": duration,
                "total_chunks": len(outputs),
                "output": "".join(o["data"] for o in outputs),
                "chunks": outputs,
            }
        except serial.SerialException as e:
            return {"success": False, "port": port, "error": f"串口错误: {e}"}
        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass


def _create_auth_middleware(auth_key: str):
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class AuthMiddleware(BaseHTTPMiddleware):
        def __init__(self, app):
            super().__init__(app)
            self.auth_key = auth_key

        async def dispatch(self, request, call_next):
            # 放行 OPTIONS 预检请求
            if request.method == "OPTIONS":
                return await call_next(request)
            # 放行健康检查路径
            if request.url.path in ("/health", "/"):
                return await call_next(request)

            auth_header = request.headers.get("authorization", "")
            api_key_header = request.headers.get("x-api-key", "")

            token = None
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:]
            elif api_key_header:
                token = api_key_header

            if token != self.auth_key:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await call_next(request)

    return AuthMiddleware


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AutoCom MCP Server (FastMCP)")
    parser.add_argument("--sse", action="store_true", help="以 SSE (HTTP) 模式运行")
    parser.add_argument("--streamable", action="store_true", help="以 Streamable HTTP 模式运行（长连接/双向通道）")
    parser.add_argument("--auth-key", type=str, default=None, help="为 HTTP 模式启用简单 API Key 鉴权")
    parser.add_argument("--port", type=int, default=8888, help="HTTP 模式监听端口（默认 8888）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="HTTP 模式监听地址（默认 0.0.0.0）")
    args = parser.parse_args()

    if not _FASTMCP_AVAILABLE:
        print("Error: fastmcp 未安装。请运行: pip install fastmcp")
        raise SystemExit(1)

    server = AutoComMCPServer(auth_key=args.auth_key)

    def _run_mcp_callable(obj, name: str, /, *a, **kw):
        """检查 obj 是否有可调用的 name 属性并运行它（如果返回协程则使用 asyncio.run）。

        如果不可用，会打印可用属性帮助排查版本兼容性问题并退出。
        """
        fn = getattr(obj, name, None)
        if fn is None or not callable(fn):
            available = [n for n in dir(obj) if not n.startswith("_")]
            msg = (
                f"FastMCP does not expose '{name}' (got None).\n"
                f"This often means installed fastmcp version is incompatible.\n"
                f"Available attributes: {available}\n"
                f"Suggested fixes: upgrade fastmcp (pip install -U fastmcp) or check its docs."
            )
            print(msg)
            logger.log_error(msg)
            raise SystemExit(1)

        try:
            res = fn(*a, **kw)
            if asyncio.iscoroutine(res):
                return _run_coroutine_with_graceful_shutdown(res)
            return res
        except Exception as e:
            logger.log_error(f"Error while running FastMCP.{name}: {e}")
            raise


    def _safe_log_info(message: str) -> None:
        """尝试使用 logger 输出信息，若底层流已关闭则回退到 stderr，避免抛出异常。"""
        try:
            logger.log_info(message)
        except Exception:
            try:
                print(message, file=sys.stderr)
            except Exception:
                pass


    def _safe_stderr_message(message: str) -> None:
        """仅写 stderr，避免 stdio 关闭后 logging handler 再次抛错。"""
        try:
            sys.stderr.write(message + "\n")
            sys.stderr.flush()
        except Exception:
            pass


    def _invoke_stdio_method(mcp_obj, auth_key=None):
        """尝试多个可能的 stdio 运行方法名以兼容不同版本的 fastmcp。

        会按候选列表依次尝试，若方法接受 `auth_key` 参数则传入。
        """
        candidates = [
            "run_stdio_async",
            "run_stdio",
            "run_stdio_server",
            "run_stdio_loop",
            "serve_stdio",
            "run_stdio_server_async",
        ]

        for name in candidates:
            fn = getattr(mcp_obj, name, None)
            if not fn or not callable(fn):
                continue
            logger.log_info(f"MCP: attempting stdio method '{name}'")
            try:
                sig = inspect.signature(fn)
            except Exception:
                sig = None

            call_kwargs = {}
            if sig:
                params = sig.parameters
                if "auth_key" in params and auth_key is not None:
                    call_kwargs["auth_key"] = auth_key
                if "server_name" in params:
                    call_kwargs["server_name"] = getattr(mcp_obj, "server_name", "autocom")

            try:
                if call_kwargs:
                    res = fn(**call_kwargs)
                else:
                    res = fn()
                if asyncio.iscoroutine(res):
                    return _run_coroutine_with_graceful_shutdown(
                        res,
                        on_interrupt=lambda: _safe_stderr_message("MCP Server 收到中断信号，正在退出..."),
                    )
                return res
            except TypeError as e:
                logger.log_info(f"MCP: TypeError calling {name}: {e}")
                continue
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as e:
                logger.log_error(f"MCP: Error while running {name}: {e}")
                raise

        available = [n for n in dir(mcp_obj) if not n.startswith("_")]
        msg = (
            f"No compatible stdio method found among {candidates}.",
            f"Available attributes: {available}",
        )
        msg_text = " ".join(map(str, msg))
        print(msg_text)
        logger.log_error(msg_text)
        raise SystemExit(1)

    # 确定运行模式
    if args.sse:
        transport = "sse"
        path = "/mcp/sse"
    elif args.streamable:
        transport = "streamable-http"
        path = "/mcp/stream"
    else:
        # stdio 模式
        try:
            _invoke_stdio_method(server.mcp, auth_key=args.auth_key)
        except (KeyboardInterrupt, asyncio.CancelledError):
            _safe_stderr_message("MCP Server 收到中断信号，正在退出...")
        return

    # 构建中间件列表
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            max_age=3600,
        )
    ]
    if args.auth_key:
        AuthMiddlewareClass = _create_auth_middleware(args.auth_key)
        middleware.append(Middleware(AuthMiddlewareClass))

    # 启动 HTTP 服务器
    logger.log_info(f"启动 {transport} 服务器: http://{args.host}:{args.port}{path}")
    try:
        _run_mcp_callable(
            server.mcp,
            "run_http_async",
            transport=transport,
            host=args.host,
            port=args.port,
            path=path,
            middleware=middleware,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        _safe_log_info("MCP Server 收到中断信号，正在退出...")


if __name__ == "__main__":
    main()