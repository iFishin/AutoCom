#!/usr/bin/env python3
"""
AutoCom MCP Server - FastMCP 重构实现

使用 FastMCP 暴露 AutoCom 的串口操作能力，支持 stdio、SSE、Streamable HTTP 三种运行模式。

工具分类：
  流水线工具：
    - run_pipeline: 执行 Steps 配置文件，支持 loop/duration 控制
    - validate_pipeline: 校验 Steps YAML/JSON 配置
    - load_pipeline: 加载并解析配置文件（支持配置合并）

  基础串口工具：
    - list_serial_ports: 列出可用串口设备
    - execute_serial_command: 底层单条指令执行
    - monitor_serial_port: 监听串口输出

  持久会话工具（多轮交互，避免反复开闭串口）：
    - serial_session_open: 开启持久串口会话
    - serial_session_send: 在会话中发送指令
    - serial_session_read: 读取会话积累数据
    - serial_session_close: 关闭会话

  硬件调试工具：
    - serial_pin_status: 读取 CTS/DSR/DCD/RI 信号线状态
    - serial_pin_set: 设置 DTR/RTS 输出电平
    - serial_loopback_test: TX/RX 回环测试
    - serial_latency_bench: 串口收发延迟基准测试
"""

from __future__ import annotations

import asyncio
import json
import time
import inspect
import contextlib
import io
import sys
import threading
import uuid
import socket
import serial
from pathlib import Path
from collections import deque
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from typing import Any, Optional, List

try:
    from fastmcp import FastMCP, Context
    from fastmcp.server.dependencies import get_context
    _FASTMCP_AVAILABLE = True
except Exception:
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
    with contextlib.suppress(Exception):
        if isinstance(exc, BaseExceptionGroup):
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


def _get_reachable_host(bind_host: str) -> str:
    """将 bind 地址（如 0.0.0.0）解析为首个非回环 IPv4 地址；否则原样返回。"""
    if bind_host != "0.0.0.0":
        return bind_host
    try:
        hostname = socket.gethostname()
        for addr in socket.getaddrinfo(hostname, None):
            family, type_, proto, canonname, sockaddr = addr
            if family == socket.AF_INET:  # IPv4
                ip = sockaddr[0]
                if not ip.startswith("127."):
                    return ip
        return socket.gethostbyname(hostname)
    except Exception:
        return "127.0.0.1"


class AutoComMCPServer:
    """基于 FastMCP 的 MCP Server，工具以装饰器方式注册到 `self.mcp`。"""

    def __init__(self, server_name: str = "autocom", auth_key: Optional[str] = None):
        if not _FASTMCP_AVAILABLE:
            raise RuntimeError("fastmcp 未安装。请运行: pip install fastmcp")

        self.auth_key = auth_key
        self.server_name = server_name
        if FastMCP is None:
            raise RuntimeError("FastMCP 类不可用，可能是 fastmcp 版本不兼容。请升级 fastmcp 或检查其文档。")
        self.mcp = FastMCP()
        # 操作审计日志
        from utils.dirs import get_dirs
        self._audit_dir = get_dirs().log_dir / "mcp_audit"
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._audit_lock = threading.Lock()
        self._audit_date: Optional[str] = None
        self._audit_fh: Optional[io.TextIOWrapper] = None
        # 持久会话管理
        self._sessions: dict[str, dict] = {}
        self._session_lock = threading.Lock()
        self._session_idle_timeout = 300.0  # 5 分钟无操作自动关闭
        self._session_cleanup_interval = 30.0  # 每 30s 扫描一次
        self._cleanup_thread = threading.Thread(target=self._session_cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        self._register_tools()

    # ======================== 操作审计日志 ========================

    _AUDIT_SENSITIVE_KEYS = frozenset({"password", "pwd", "passwd", "auth_key", "api_key", "secret", "token"})

    def _sanitize_params(self, params: dict) -> dict:
        """脱敏：递归过滤敏感字段。"""
        if not isinstance(params, dict):
            return params
        result = {}
        for k, v in params.items():
            if isinstance(k, str) and k.lower() in self._AUDIT_SENSITIVE_KEYS:
                result[k] = "***"
            elif isinstance(v, dict):
                result[k] = self._sanitize_params(v)
            else:
                result[k] = v
        return result

    def _audit_log(self, entry: dict) -> None:
        """写入审计日志（线程安全、按日轮转）。"""
        import datetime as dt

        now = dt.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        entry["@timestamp"] = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + now.strftime("%z")

        with self._audit_lock:
            # 按日轮转
            if date_str != self._audit_date:
                if self._audit_fh is not None:
                    try:
                        self._audit_fh.close()
                    except Exception:
                        pass
                log_path = self._audit_dir / f"{date_str}.jsonl"
                try:
                    fh = open(log_path, "a", encoding="utf-8")
                    self._audit_fh = fh
                    self._audit_date = date_str
                except Exception as e:
                    logger.log_error(f"Cannot open audit log file {log_path}: {e}")
                    return
            fh = self._audit_fh
            if fh is None:
                return
            try:
                line = json.dumps(entry, ensure_ascii=False, default=str)
                fh.write(line + "\n")
                fh.flush()
            except Exception as e:
                logger.log_error(f"Failed to write audit log: {e}")

    def _audit_log_tool(self, tool_name: str, params: dict, result: dict, elapsed_ms: float = 0) -> None:
        """便捷包装：从工具调用中记录审计日志。"""
        audit_entry = {
            "type": "tool_call",
            "tool": tool_name,
            "params": self._sanitize_params(params),
            "result_status": "success" if result.get("success") else "failed",
            "elapsed_ms": round(elapsed_ms, 1),
        }
        # 提取公共字段方便查询
        for key in ("port", "session_id", "file_path", "mode", "command"):
            if key in params:
                audit_entry[key] = params[key]
        result_error = result.get("error")
        if result_error:
            audit_entry["error"] = str(result_error)
        self._audit_log(audit_entry)

    @property
    def audit_log_path(self) -> str:
        """审计日志目录路径，用户可查阅。"""
        return str(self._audit_dir)

    def _register_tools(self) -> None:
        mcp = self.mcp

        @mcp.tool()
        async def list_serial_ports() -> dict:
            """列出当前可用的串口设备及其信息"""
            logger.log_info("MCP: list_serial_ports called")
            t0 = time.time()
            result = await AutoComMCPServer._list_serial_ports()
            self._audit_log_tool("list_serial_ports", {}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def execute_serial_command(
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
            """向指定串口设备发送单条指令并返回响应（底层调试用）"""
            logger.log_info(f"MCP: execute_serial_command on {port}")
            t0 = time.time()
            result = await AutoComMCPServer._execute_serial_command(
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
            self._audit_log_tool("execute_serial_command", {
                "port": port, "command": command, "baud_rate": baud_rate,
                "timeout": timeout, "device_name": device_name,
            }, result, result.get("elapsed_ms", 0))
            return result

        @mcp.tool()
        async def monitor_serial_port(
            port: str,
            baud_rate: int = 115200,
            duration: float = 10.0,
            heartbeat_interval: float = 0.3,
        ) -> dict:
            """实时监听串口并通过 MCP progress 通知持续推送数据。

            注意：FastMCP 对工具返回的 async generator 会先整体物化，因此不能用于真正逐条实时回传。
            本方法改为在工具执行过程中通过 progress message 持续发送数据，最后返回一次汇总。
            """
            logger.log_info(f"MCP: monitor_serial_port {port} duration={duration} heartbeat={heartbeat_interval}")

            progress_token = None
            ctx: Optional[Any] = None
            try:
                ctx = get_context() if callable(get_context) else None
                if ctx and ctx.request_context and ctx.request_context.meta:
                    progress_token = ctx.request_context.meta.progressToken
            except Exception:
                progress_token = None

            progress_enabled = progress_token is not None
            _audit_params = {"port": port, "baud_rate": baud_rate, "duration": duration}
            if duration <= 0 and not progress_enabled:
                result = {
                    "success": False,
                    "port": port,
                    "error": "Client does not support progressToken and duration<=0 would hang. Pass duration>0 or use a progress-capable MCP client.",
                }
                self._audit_log_tool("monitor_serial_port", _audit_params, result)
                return result

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
                result = {"success": False, "port": port, "error": str(e)}
                self._audit_log_tool("monitor_serial_port", _audit_params, result)
                return result

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
                result = {
                    "success": True,
                    "port": port,
                    "duration_seconds": round(time.time() - start_time, 3),
                    "progress_enabled": progress_enabled,
                    "total_chunks": chunk_count,
                    "total_bytes": byte_count,
                    "tail_chunks": list(outputs),
                }
                self._audit_log_tool("monitor_serial_port", _audit_params, result, result["duration_seconds"] * 1000)
                return result
            except (KeyboardInterrupt, asyncio.CancelledError):
                await _emit("cancelled")
                result = {
                    "success": True,
                    "port": port,
                    "cancelled": True,
                    "duration_seconds": round(time.time() - start_time, 3),
                    "progress_enabled": progress_enabled,
                    "total_chunks": chunk_count,
                    "total_bytes": byte_count,
                    "tail_chunks": list(outputs),
                }
                self._audit_log_tool("monitor_serial_port", _audit_params, result, result["duration_seconds"] * 1000)
                return result
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

        @mcp.tool()
        async def load_pipeline(
            file_path: str,
            config_path: Optional[str] = None,
            config_overrides: Optional[dict] = None,
        ) -> dict:
            """加载并解析 AutoCom Steps 配置文件（YAML/JSON），支持配置合并与覆盖。

            返回设备列表、步骤列表、常量、配置摘要等信息。
            """
            logger.log_info(f"MCP: load_pipeline {file_path}")
            t0 = time.time()
            result = await AutoComMCPServer._load_pipeline(
                file_path=file_path,
                config_path=config_path,
                config_overrides=config_overrides,
            )
            self._audit_log_tool("load_pipeline", {"file_path": file_path, "config_path": config_path}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def validate_pipeline(
            file_path: str,
            config_path: Optional[str] = None,
            config_overrides: Optional[dict] = None,
        ) -> dict:
            """校验 AutoCom Steps 配置文件（YAML/JSON），返回错误与告警列表。"""
            logger.log_info(f"MCP: validate_pipeline {file_path}")
            t0 = time.time()
            result = await AutoComMCPServer._validate_pipeline(
                file_path=file_path,
                config_path=config_path,
                config_overrides=config_overrides,
            )
            self._audit_log_tool("validate_pipeline", {"file_path": file_path}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def run_pipeline(
            file_path: str,
            config_path: Optional[str] = None,
            config_overrides: Optional[dict] = None,
            loop_count: Optional[int] = None,
            duration: Optional[str] = None,
            infinite: bool = False,
            stop_on_failure: Optional[bool] = None,
            max_failures: Optional[int] = None,
            interval_ms: Optional[int] = None,
        ) -> dict:
            """执行 AutoCom Steps 配置文件（完整流水线执行）。

            参数对齐当前 AutoCom 执行配置：
            - loop_count: 循环轮数（对应 -n/--count）
            - duration: 限时执行时长，如 "30s", "5m", "1h"（对应 --duration）
            - infinite: 无限循环（对应 --infinite）
            - stop_on_failure: 失败即停止
            - max_failures: 最大失败次数
            - interval_ms: 轮次间隔毫秒数
            """
            logger.log_info(
                f"MCP: run_pipeline {file_path} loop={loop_count} duration={duration} infinite={infinite}"
            )
            t0 = time.time()
            result = await AutoComMCPServer._run_pipeline(
                file_path=file_path,
                config_path=config_path,
                config_overrides=config_overrides,
                loop_count=loop_count,
                duration=duration,
                infinite=infinite,
                stop_on_failure=stop_on_failure,
                max_failures=max_failures,
                interval_ms=interval_ms,
            )
            self._audit_log_tool("run_pipeline", {
                "file_path": file_path, "loop_count": loop_count,
                "duration": duration, "infinite": infinite,
            }, result, result.get("elapsed_seconds", 0) * 1000)
            return result

    # ======================== 持久会话工具 ========================

        @mcp.tool()
        async def serial_session_open(
            port: str,
            baud_rate: int = 115200,
            data_bits: int = 8,
            stop_bits: int = 1,
            parity: str = "none",
            timeout: float = 5.0,
            flow_control: bool = False,
            label: Optional[str] = None,
            monitor: bool = False,
        ) -> dict:
            """开启一个持久串口会话，返回 session_id。
            后续可通过 session_id 复用此连接，避免反复打开/关闭串口。
            设置 monitor=True 可让后台持续接收串口数据，通过 serial_session_read 随时读取。
            """
            logger.log_info(f"MCP: serial_session_open {port} @ {baud_rate}")
            t0 = time.time()
            result = await self._serial_session_open(
                port=port, baud_rate=baud_rate,
                data_bits=data_bits, stop_bits=stop_bits,
                parity=parity, timeout=timeout,
                flow_control=flow_control, label=label or port,
                monitor=monitor,
            )
            self._audit_log_tool("serial_session_open", {
                "port": port, "baud_rate": baud_rate, "label": label,
            }, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def serial_session_send(
            session_id: str,
            command: str,
            timeout: Optional[float] = None,
            line_ending: str = "0d0a",
            hex_mode: bool = False,
            expected_responses: Optional[List[str]] = None,
        ) -> dict:
            """在持久会话中发送指令，等待响应后返回。"""
            logger.log_info(f"MCP: serial_session_send {session_id}")
            t0 = time.time()
            result = await self._serial_session_send(
                session_id=session_id, command=command,
                timeout=timeout, line_ending=line_ending,
                hex_mode=hex_mode, expected_responses=expected_responses,
            )
            self._audit_log_tool("serial_session_send", {
                "session_id": session_id, "command": command,
            }, result, result.get("elapsed_ms", 0))
            return result

        @mcp.tool()
        async def serial_session_read(
            session_id: str,
            timeout: Optional[float] = None,
            max_bytes: Optional[int] = None,
        ) -> dict:
            """读取持久会话中积累的缓冲区数据。"""
            logger.log_info(f"MCP: serial_session_read {session_id}")
            t0 = time.time()
            result = await self._serial_session_read(
                session_id=session_id, timeout=timeout, max_bytes=max_bytes,
            )
            self._audit_log_tool("serial_session_read", {
                "session_id": session_id,
            }, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def serial_session_close(session_id: str) -> dict:
            """关闭并清理持久串口会话。"""
            logger.log_info(f"MCP: serial_session_close {session_id}")
            t0 = time.time()
            result = await self._serial_session_close(session_id=session_id)
            self._audit_log_tool("serial_session_close", {"session_id": session_id}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def serial_session_list() -> dict:
            """列出当前所有活跃的持久串口会话及其统计信息。"""
            logger.log_info("MCP: serial_session_list called")
            t0 = time.time()
            result = await self._serial_session_list()
            self._audit_log_tool("serial_session_list", {}, result, (time.time() - t0) * 1000)
            return result

    # ======================== 硬件调试工具 ========================

        @mcp.tool()
        async def serial_pin_status(port: str, baud_rate: int = 115200) -> dict:
            """读取串口信号线状态：CTS/DSR/DCD/RI。
            可用于排查设备连接是否正常（如 DSR 低电平可能表示设备未就绪）。
            """
            logger.log_info(f"MCP: serial_pin_status {port}")
            t0 = time.time()
            result = await AutoComMCPServer._serial_pin_status(port=port, baud_rate=baud_rate)
            self._audit_log_tool("serial_pin_status", {"port": port}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def serial_pin_set(
            port: str,
            dtr: Optional[bool] = None,
            rts: Optional[bool] = None,
            baud_rate: int = 115200,
        ) -> dict:
            """设置串口 DTR/RTS 输出电平。
            可用于硬件复位（如 DTR 低→高触发 MCU 重启）或流控测试。
            """
            logger.log_info(f"MCP: serial_pin_set {port}")
            t0 = time.time()
            result = await AutoComMCPServer._serial_pin_set(
                port=port, dtr=dtr, rts=rts, baud_rate=baud_rate,
            )
            self._audit_log_tool("serial_pin_set", {"port": port, "dtr": dtr, "rts": rts}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def serial_loopback_test(
            port: str,
            baud_rate: int = 115200,
            mode: str = "hardware",
            test_data: Optional[str] = None,
            probe_command: str = "AT",
            probe_expected: str = "OK",
            timeout: float = 3.0,
        ) -> dict:
            """串口回环测试。
            mode=hardware: 发 test_data 然后读回，需物理短接 TX→RX。
            mode=echo: 发 probe_command 检查是否收到 probe_expected。
            """
            logger.log_info(f"MCP: serial_loopback_test {port} mode={mode}")
            t0 = time.time()
            result = await AutoComMCPServer._serial_loopback_test(
                port=port, baud_rate=baud_rate, mode=mode,
                test_data=test_data, probe_command=probe_command,
                probe_expected=probe_expected, timeout=timeout,
            )
            self._audit_log_tool("serial_loopback_test", {
                "port": port, "mode": mode,
            }, result, result.get("elapsed_ms", (time.time() - t0) * 1000))
            return result

        @mcp.tool()
        async def serial_latency_bench(
            port: str,
            baud_rate: int = 115200,
            rounds: int = 10,
            test_data: str = "AT",
            timeout: float = 5.0,
        ) -> dict:
            """串口收发延迟基准测试。
            多次发送指令并测量：发送耗时、首字节到达耗时、完整往返耗时。
            """
            logger.log_info(f"MCP: serial_latency_bench {port} rounds={rounds}")
            t0 = time.time()
            result = await AutoComMCPServer._serial_latency_bench(
                port=port, baud_rate=baud_rate, rounds=rounds,
                test_data=test_data, timeout=timeout,
            )
            self._audit_log_tool("serial_latency_bench", {
                "port": port, "rounds": rounds,
            }, result, (time.time() - t0) * 1000)
            return result

        # ======================== 流水线配置管理 ========================

        @mcp.tool()
        async def pipeline_list(base_dir: Optional[str] = None) -> dict:
            """列出指定目录下所有可用的流水线配置文件（YAML/JSON）"""
            logger.log_info("MCP: pipeline_list called")
            t0 = time.time()
            result = await AutoComMCPServer._pipeline_list(base_dir=base_dir)
            self._audit_log_tool("pipeline_list", {"base_dir": base_dir or "(default)"}, result, (time.time() - t0) * 1000)
            return result

        # ======================== 执行历史与分析 ========================

        @mcp.tool()
        async def execution_list(limit: int = 20) -> dict:
            """列出最近执行会话（从 device_logs/ 读取）"""
            logger.log_info("MCP: execution_list called")
            t0 = time.time()
            result = await AutoComMCPServer._execution_list(limit=limit)
            self._audit_log_tool("execution_list", {"limit": limit}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def execution_report(session_id: str) -> dict:
            """解析指定执行会话的日志和结果"""
            logger.log_info(f"MCP: execution_report {session_id}")
            t0 = time.time()
            result = await AutoComMCPServer._execution_report(session_id=session_id)
            self._audit_log_tool("execution_report", {"session_id": session_id}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def session_log_query(session_id: str, keyword: str, max_results: int = 50) -> dict:
            """在指定执行会话的设备日志中搜索关键词"""
            logger.log_info(f"MCP: session_log_query {session_id} keyword={keyword}")
            t0 = time.time()
            result = await AutoComMCPServer._session_log_query(
                session_id=session_id, keyword=keyword, max_results=max_results,
            )
            self._audit_log_tool("session_log_query", {
                "session_id": session_id, "keyword": keyword,
            }, result, (time.time() - t0) * 1000)
            return result

        # ======================== 串口调试增强 ========================

        @mcp.tool()
        async def serial_baud_scan(port: str, test_command: str = "AT", expected_response: str = "OK",
                                    line_ending: str = "0d0a") -> dict:
            """自动尝试常用波特率（9600~921600），找到能收到期望响应的那个。
            排查"连不上"问题时的第一选择。
            """
            logger.log_info(f"MCP: serial_baud_scan {port} test={test_command}")
            t0 = time.time()
            result = await AutoComMCPServer._serial_baud_scan(
                port=port, test_command=test_command, expected_response=expected_response,
                line_ending=line_ending,
            )
            self._audit_log_tool("serial_baud_scan", {"port": port}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def serial_hex_dump(port: str, baud_rate: int = 115200,
                                    bytes_to_read: int = 256, timeout: float = 3.0) -> dict:
            """以 hex + ASCII 格式读取串口数据，排查乱码和不可见字符问题"""
            logger.log_info(f"MCP: serial_hex_dump {port} baud={baud_rate}")
            t0 = time.time()
            result = await AutoComMCPServer._serial_hex_dump(
                port=port, baud_rate=baud_rate, bytes_to_read=bytes_to_read, timeout=timeout,
            )
            self._audit_log_tool("serial_hex_dump", {"port": port, "baud_rate": baud_rate}, result, (time.time() - t0) * 1000)
            return result

        # ======================== 设备参数管理 ========================

        @mcp.tool()
        async def device_profile_list() -> dict:
            """列出所有已保存的设备串口配置"""
            logger.log_info("MCP: device_profile_list called")
            t0 = time.time()
            result = await AutoComMCPServer._device_profile_list()
            self._audit_log_tool("device_profile_list", {}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def device_profile_save(
            name: str, port: str, baud_rate: int = 115200,
            data_bits: int = 8, stop_bits: int = 1,
            parity: str = "none", flow_control: bool = False,
            timeout: float = 5.0, label: str = "",
        ) -> dict:
            """保存设备串口配置。之后可通过 profile=NAME 快速打开会话"""
            logger.log_info(f"MCP: device_profile_save {name} -> {port}")
            t0 = time.time()
            result = await AutoComMCPServer._device_profile_save(
                name=name, port=port, baud_rate=baud_rate,
                data_bits=data_bits, stop_bits=stop_bits,
                parity=parity, flow_control=flow_control,
                timeout=timeout, label=label,
            )
            self._audit_log_tool("device_profile_save", {"name": name, "port": port}, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def device_profile_delete(name: str) -> dict:
            """删除已保存的设备串口配置"""
            logger.log_info(f"MCP: device_profile_delete {name}")
            t0 = time.time()
            result = await AutoComMCPServer._device_profile_delete(name=name)
            self._audit_log_tool("device_profile_delete", {"name": name}, result, (time.time() - t0) * 1000)
            return result

        # ======================== 单步调试 ========================

        @mcp.tool()
        async def pipeline_step_debug(file_path: str, step_id: str,
                                        config_overrides: Optional[dict] = None) -> dict:
            """只执行流水线中的某一个步骤，方便单独调试某条指令"""
            logger.log_info(f"MCP: pipeline_step_debug {file_path} step={step_id}")
            t0 = time.time()
            result = await AutoComMCPServer._pipeline_step_debug(
                file_path=file_path, step_id=step_id, config_overrides=config_overrides,
            )
            self._audit_log_tool("pipeline_step_debug", {
                "file_path": file_path, "step_id": step_id,
            }, result, (time.time() - t0) * 1000)
            return result

        @mcp.tool()
        async def pipeline_dry_run(file_path: str, config_overrides: Optional[dict] = None) -> dict:
            """对流水线做干运行：解析变量、追踪控制流，但不执行实际 I/O"""
            logger.log_info(f"MCP: pipeline_dry_run {file_path}")
            t0 = time.time()
            result = await AutoComMCPServer._pipeline_dry_run(
                file_path=file_path, config_overrides=config_overrides,
            )
            self._audit_log_tool("pipeline_dry_run", {"file_path": file_path}, result, (time.time() - t0) * 1000)
            return result

    # ------------------------- 工具实现 -------------------------

    @staticmethod
    async def _list_serial_ports() -> dict:
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
        return {"success": True, "total": len(devices), "devices": devices}

    @staticmethod
    async def _execute_serial_command(
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
        """执行单条串口指令，复用 AutoCom 的命令执行逻辑。"""
        import serial

        # 解析换行符
        line_ending_bytes = bytes.fromhex(line_ending) if line_ending else b"\r\n"

        # 处理十六进制发送
        if hex_mode:
            try:
                send_bytes = bytes.fromhex(command.replace(" ", ""))
            except ValueError as e:
                return {"success": False, "port": port, "error": f"Invalid hex command: {e}"}
        else:
            send_bytes = command.encode("utf-8")

        ser = None
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
            )

            # 发送指令
            ser.write(send_bytes + line_ending_bytes)
            ser.flush()

            # 读取响应
            start_time = time.time()
            response = b""
            expected = expected_responses or []
            complete_patterns = completion_rules.get("complete", []) if completion_rules else []
            terminal_patterns = completion_rules.get("terminal", ["OK", "ERROR"]) if completion_rules else ["OK", "ERROR"]

            while time.time() - start_time < timeout:
                avail = ser.in_waiting
                if avail > 0:
                    chunk = ser.read(avail)
                    response += chunk
                    text = response.decode("utf-8", errors="replace")

                    # 检查完成条件
                    if complete_patterns:
                        for pat in complete_patterns:
                            if pat in text:
                                return {
                                    "success": True,
                                    "port": port,
                                    "command": command,
                                    "response": text,
                                    "matched_pattern": pat,
                                    "elapsed_ms": int((time.time() - start_time) * 1000),
                                }

                    # 检查预期响应
                    if expected:
                        for exp in expected:
                            if exp in text:
                                return {
                                    "success": True,
                                    "port": port,
                                    "command": command,
                                    "response": text,
                                    "matched_expected": exp,
                                    "elapsed_ms": int((time.time() - start_time) * 1000),
                                }

                    # 检查终止条件
                    if terminal_patterns:
                        for pat in terminal_patterns:
                            if pat in text:
                                return {
                                    "success": True,
                                    "port": port,
                                    "command": command,
                                    "response": text,
                                    "matched_terminal": pat,
                                    "elapsed_ms": int((time.time() - start_time) * 1000),
                                }

                await asyncio.sleep(0.02)

            # 超时返回已收到的数据
            text = response.decode("utf-8", errors="replace")
            return {
                "success": len(response) > 0,
                "port": port,
                "command": command,
                "response": text,
                "elapsed_ms": int((time.time() - start_time) * 1000),
                "timeout": True,
            }

        except serial.SerialException as e:
            return {"success": False, "port": port, "error": f"Serial error: {e}"}
        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    @staticmethod
    async def _load_pipeline(
        file_path: str,
        config_path: Optional[str] = None,
        config_overrides: Optional[dict] = None,
    ) -> dict:
        """加载并解析 Steps 配置文件，支持配置文件合并与覆盖。"""
        from AutoCom import load_commands_from_file, merge_config

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            # 加载主配置
            pipeline_data = load_commands_from_file(path)

            # 加载并合并额外配置文件
            if config_path:
                config_file = Path(config_path)
                if config_file.exists():
                    extra_config = load_commands_from_file(config_file)
                    pipeline_data = merge_config(pipeline_data, extra_config)

            # 应用内联覆盖
            if config_overrides:
                pipeline_data = merge_config(pipeline_data, config_overrides)

            # 生成摘要
            summary = {
                "file_path": str(path.resolve()),
                "config_merged": config_path is not None,
                "steps_count": len(pipeline_data.get("Steps", [])),
                "devices_count": len(pipeline_data.get("Devices", [])),
                "constants_count": len(pipeline_data.get("Constants", {})),
                "config_mode": pipeline_data.get("Config", {}).get("mode", "single"),
                "description": pipeline_data.get("Config", {}).get("description", ""),
            }

            return {
                "success": True,
                "file_path": str(path.resolve()),
                "config_merged": config_path is not None,
                "summary": summary,
                "data": pipeline_data,
            }
        except Exception as e:
            logger.log_error(f"Error loading pipeline: {e}")
            return {"success": False, "file_path": file_path, "error": str(e)}

    @staticmethod
    async def _validate_pipeline(
        file_path: str,
        config_path: Optional[str] = None,
        config_overrides: Optional[dict] = None,
    ) -> dict:
        """校验 Steps 配置文件。"""
        from AutoCom import load_commands_from_file, merge_config

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            pipeline_data = load_commands_from_file(path)

            if config_path:
                config_file = Path(config_path)
                if config_file.exists():
                    extra_config = load_commands_from_file(config_file)
                    pipeline_data = merge_config(pipeline_data, extra_config)

            if config_overrides:
                pipeline_data = merge_config(pipeline_data, config_overrides)

            issues: List[dict] = []
            warnings: List[dict] = []

            if not isinstance(pipeline_data, dict):
                issues.append({"path": "$", "message": "Config root must be a dict"})
            else:
                devices = pipeline_data.get("Devices") or []
                steps = pipeline_data.get("Steps") or []

                if not devices:
                    issues.append({"path": "Devices", "message": "Devices must not be empty"})
                if not steps:
                    issues.append({"path": "Steps", "message": "Steps must not be empty"})

                # 检查设备
                enabled_names = set()
                if isinstance(devices, list):
                    for idx, dev in enumerate(devices):
                        if not isinstance(dev, dict):
                            issues.append({"path": f"Devices[{idx}]", "message": "Device entry must be an object"})
                            continue
                        name = dev.get("name")
                        if not name:
                            issues.append({"path": f"Devices[{idx}].name", "message": "Device must have a 'name' field"})
                        if dev.get("status", "enabled") != "disabled" and name:
                            enabled_names.add(name)

                # 检查步骤
                if isinstance(steps, list):
                    for idx, step in enumerate(steps):
                        if not isinstance(step, dict):
                            issues.append({"path": f"Steps[{idx}]", "message": "Step entry must be an object"})
                            continue

                        step_id = step.get("id", f"steps[{idx}]")
                        step_type = step.get("type")

                        if not step_type:
                            issues.append({"path": f"Steps[{idx}].type", "message": f"Step '{step_id}' missing 'type' field"})

                        dev_name = step.get("device")
                        if dev_name:
                            if enabled_names and dev_name not in enabled_names:
                                warnings.append({
                                    "path": f"Steps[{idx}].device",
                                    "message": f"Step '{step_id}' references unknown device '{dev_name}'",
                                })

                        timeout = step.get("timeout")
                        if timeout is not None:
                            try:
                                tv = float(timeout)
                                if tv <= 0:
                                    issues.append({"path": f"Steps[{idx}].timeout", "message": "timeout must be > 0"})
                            except Exception:
                                issues.append({"path": f"Steps[{idx}].timeout", "message": "timeout must be numeric"})

            return {
                "success": len(issues) == 0,
                "file_path": str(path.resolve()),
                "issue_count": len(issues),
                "warning_count": len(warnings),
                "errors": issues,
                "warnings": warnings,
            }
        except Exception as e:
            logger.log_error(f"Error validating pipeline: {e}")
            return {"success": False, "file_path": file_path, "error": str(e)}

    @staticmethod
    async def _run_pipeline(
        file_path: str,
        config_path: Optional[str] = None,
        config_overrides: Optional[dict] = None,
        loop_count: Optional[int] = None,
        duration: Optional[str] = None,
        infinite: bool = False,
        stop_on_failure: Optional[bool] = None,
        max_failures: Optional[int] = None,
        interval_ms: Optional[int] = None,
    ) -> dict:
        """执行完整的 Steps 流水线。"""
        from AutoCom import execute_with_loop, resolve_execution_config, load_commands_from_file, merge_config

        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            # 加载配置
            dict_data = load_commands_from_file(str(path))

            if config_path:
                config_file = Path(config_path)
                if config_file.exists():
                    extra_config = load_commands_from_file(str(config_file))
                    dict_data = merge_config(dict_data, extra_config)

            if config_overrides:
                dict_data = merge_config(dict_data, config_overrides)

            # 解析执行配置（CLI 参数优先）
            exec_cfg = resolve_execution_config(
                dict_data,
                cli_loop=loop_count,
                cli_infinite=infinite,
            )

            # 应用额外覆盖
            if stop_on_failure is not None:
                exec_cfg.stop_on_failure = stop_on_failure
            if max_failures is not None:
                exec_cfg.max_failures = max_failures
            if interval_ms is not None:
                exec_cfg.interval_ms = interval_ms
            if duration:
                from AutoCom import parse_duration
                exec_cfg.duration_seconds = parse_duration(duration)

            # 执行
            start_time = time.time()
            execute_with_loop(str(path), config=dict_data)
            elapsed = time.time() - start_time

            return {
                "success": True,
                "file_path": str(path.resolve()),
                "executed_iterations": exec_cfg.iterations,
                "mode": exec_cfg.mode,
                "elapsed_seconds": round(elapsed, 3),
            }
        except Exception as e:
            logger.log_error(f"Error running pipeline: {e}")
            return {"success": False, "file_path": file_path, "error": str(e)}

    # ======================== 持久会话实现 ========================

    async def _serial_session_open(
        self,
        port: str,
        baud_rate: int = 115200,
        data_bits: int = 8,
        stop_bits: int = 1,
        parity: str = "none",
        timeout: float = 5.0,
        flow_control: bool = False,
        label: str = "",
        monitor: bool = False,
    ) -> dict:
        """开启持久串口会话。"""
        _parity_map = {
            "none": serial.PARITY_NONE,
            "even": serial.PARITY_EVEN,
            "odd": serial.PARITY_ODD,
            "mark": serial.PARITY_MARK,
            "space": serial.PARITY_SPACE,
        }
        _stopbits_map = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}
        _bytesize_map = {5: serial.FIVEBITS, 6: serial.SIXBITS, 7: serial.SEVENBITS, 8: serial.EIGHTBITS}

        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=_bytesize_map.get(data_bits, serial.EIGHTBITS),
                parity=_parity_map.get(parity.lower(), serial.PARITY_NONE),
                stopbits=_stopbits_map.get(stop_bits, serial.STOPBITS_ONE),
                timeout=timeout,
                rtscts=flow_control,
            )
        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}

        session_id = uuid.uuid4().hex[:12]
        now = time.time()
        session_info = {
            "serial": ser,
            "port": port,
            "baud_rate": baud_rate,
            "label": label,
            "created_at": now,
            "last_activity": now,
            "closing": False,
            "bytes_sent": 0,
            "bytes_received": 0,
            "monitor": monitor,
            "monitor_thread": None,
            "monitor_buffer": deque(maxlen=5000),
            "monitor_started": 0.0,
            "monitor_bytes": 0,
        }
        with self._session_lock:
            self._sessions[session_id] = session_info

        if monitor:
            session_info["monitor_started"] = time.time()
            self._start_background_monitor(session_id, session_info)

        return {
            "success": True,
            "session_id": session_id,
            "port": port,
            "baud_rate": baud_rate,
            "label": label,
            "monitor": monitor,
        }

    def _start_background_monitor(self, session_id: str, session: dict) -> None:
        """为 session 启动后台串口读取守护线程（monitor 模式）。"""
        def _read_loop():
            ser = session["serial"]
            while not session.get("closing"):
                try:
                    avail = ser.in_waiting
                    if avail > 0:
                        data = ser.read(avail)
                        if data:
                            session["monitor_buffer"].append(data)
                            session["monitor_bytes"] += len(data)
                            session["bytes_received"] += len(data)
                            session["last_activity"] = time.time()
                    else:
                        time.sleep(0.01)
                except Exception:
                    if not session.get("closing"):
                        time.sleep(0.05)

        thread = threading.Thread(target=_read_loop, daemon=True, name=f"mon-{session_id}")
        thread.start()
        session["monitor_thread"] = thread

    async def _serial_session_send(
        self,
        session_id: str,
        command: str,
        timeout: Optional[float] = None,
        line_ending: str = "0d0a",
        hex_mode: bool = False,
        expected_responses: Optional[List[str]] = None,
    ) -> dict:
        """在持久会话中发送指令。"""
        with self._session_lock:
            session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": f"Session not found: {session_id}"}
        if session.get("closing"):
            return {"success": False, "error": f"Session {session_id} is closing"}

        ser: serial.Serial = session["serial"]
        effective_timeout = timeout if timeout is not None else ser.timeout or 5.0

        # 解析换行符
        le_bytes = bytes.fromhex(line_ending.replace(" ", "")) if line_ending else b"\r\n"

        # 指令编码
        if hex_mode:
            try:
                cmd_bytes = bytes.fromhex(command.replace(" ", ""))
            except ValueError as e:
                return {"success": False, "error": f"Invalid hex command: {e}"}
        else:
            cmd_bytes = command.encode("utf-8")

        send_bytes = cmd_bytes + le_bytes
        start_time = time.time()

        try:
            ser.write(send_bytes)
            ser.flush()
            session["bytes_sent"] += len(send_bytes)
        except Exception as e:
            return {"success": False, "error": f"Write failed: {e}", "session_id": session_id}

        # 读取响应
        response = b""
        expected = expected_responses or []

        while time.time() - start_time < effective_timeout:
            if session.get("closing"):
                break
            try:
                avail = ser.in_waiting
            except Exception:
                avail = 0
            if avail > 0:
                try:
                    chunk = ser.read(avail)
                except Exception:
                    break
                response += chunk
                session["bytes_received"] += len(chunk)
                session["last_activity"] = time.time()

                # 检查预期响应
                text = response.decode("utf-8", errors="replace")
                matched = [p for p in expected if p in text] if expected else []
                if matched:
                    return {
                        "success": True,
                        "session_id": session_id,
                        "port": session["port"],
                        "command": command,
                        "response": text,
                        "matched": matched,
                        "elapsed_ms": int((time.time() - start_time) * 1000),
                    }

            await asyncio.sleep(0.02)

        text = response.decode("utf-8", errors="replace")
        elapsed = int((time.time() - start_time) * 1000)
        return {
            "success": len(response) > 0 or not expected_responses,
            "session_id": session_id,
            "port": session["port"],
            "command": command,
            "response": text,
            "matched": [],
            "elapsed_ms": elapsed,
            "timeout": elapsed >= effective_timeout * 1000,
        }

    async def _serial_session_read(
        self,
        session_id: str,
        timeout: Optional[float] = None,
        max_bytes: Optional[int] = None,
    ) -> dict:
        """读取持久会话中积累的缓冲区数据。"""
        with self._session_lock:
            session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": f"Session not found: {session_id}"}
        if session.get("closing"):
            return {"success": False, "error": f"Session {session_id} is closing"}

        # monitor 模式：直接读取缓冲区
        if session.get("monitor"):
            response = b""
            with self._session_lock:
                while session["monitor_buffer"]:
                    chunk = session["monitor_buffer"].popleft()
                    response += chunk
                    if max_bytes and len(response) >= max_bytes:
                        response = response[:max_bytes]
                        break
            text = response.decode("utf-8", errors="replace")
            return {
                "success": True,
                "session_id": session_id,
                "port": session["port"],
                "data_text": text,
                "data_hex": response.hex(" "),
                "bytes": len(response),
                "elapsed_ms": 0,
                "from_buffer": True,
            }

        # 非 monitor 模式：直接读取串口
        ser: serial.Serial = session["serial"]
        effective_timeout = timeout if timeout is not None else 0.5
        start_time = time.time()
        response = b""

        while time.time() - start_time < effective_timeout:
            if session.get("closing"):
                break
            try:
                avail = ser.in_waiting
            except Exception:
                avail = 0
            if avail > 0:
                try:
                    chunk = ser.read(avail)
                except Exception:
                    break
                response += chunk
                session["bytes_received"] += len(chunk)
                session["last_activity"] = time.time()
                if max_bytes and len(response) >= max_bytes:
                    response = response[:max_bytes]
                    break
            else:
                if response:
                    break
            await asyncio.sleep(0.02)

        text = response.decode("utf-8", errors="replace")
        return {
            "success": True,
            "session_id": session_id,
            "port": session["port"],
            "data_text": text,
            "data_hex": response.hex(" "),
            "bytes": len(response),
            "elapsed_ms": int((time.time() - start_time) * 1000),
        }

    async def _serial_session_close(self, session_id: str) -> dict:
        """关闭持久会话。"""
        # 先标记 closing，阻止 send/read 访问
        with self._session_lock:
            session = self._sessions.get(session_id)
            if session:
                session["closing"] = True

        if not session:
            return {"success": False, "error": f"Session not found: {session_id}"}

        # mark closing to block send/read, then wait for monitor thread
        monitor_thread = session.get("monitor_thread")
        if monitor_thread and monitor_thread.is_alive():
            monitor_thread.join(timeout=2)

        # 从字典中移除
        with self._session_lock:
            self._sessions.pop(session_id, None)

        ser: serial.Serial = session["serial"]
        try:
            ser.close()
        except Exception as e:
            return {"success": False, "session_id": session_id, "error": str(e)}

        return {
            "success": True,
            "session_id": session_id,
            "port": session["port"],
            "duration_seconds": round(time.time() - session["created_at"], 1),
            "bytes_sent": session["bytes_sent"],
            "bytes_received": session["bytes_received"],
        }

    async def _serial_session_list(self) -> dict:
        """列出所有活跃的持久会话。"""
        sessions = []
        with self._session_lock:
            for sid, session in self._sessions.items():
                entry = {
                    "session_id": sid,
                    "port": session["port"],
                    "baud_rate": session["baud_rate"],
                    "label": session.get("label", ""),
                    "created_at": round(session["created_at"], 1),
                    "idle_seconds": round(time.time() - session["last_activity"], 1),
                    "bytes_sent": session["bytes_sent"],
                    "bytes_received": session["bytes_received"],
                }
                if session.get("monitor"):
                    entry["monitor"] = True
                    entry["monitor_bytes"] = session["monitor_bytes"]
                    entry["monitor_duration_seconds"] = round(
                        time.time() - session["monitor_started"], 1
                    )
                sessions.append(entry)
        return {
            "success": True,
            "total": len(sessions),
            "sessions": sessions,
        }

    def _session_cleanup_worker(self) -> None:
        """后台守护线程：定期清理超时空闲会话。"""
        while True:
            time.sleep(self._session_cleanup_interval)
            now = time.time()
            stale_ids = []
            with self._session_lock:
                for sid, session in list(self._sessions.items()):
                    if session.get("closing"):
                        # 已在关闭中的会话，由 close() 负责移除
                        continue
                    idle = now - session.get("last_activity", session["created_at"])
                    if idle > self._session_idle_timeout:
                        stale_ids.append(sid)
                        session["closing"] = True
            for sid in stale_ids:
                with self._session_lock:
                    session = self._sessions.pop(sid, None)
                if session:
                    try:
                        session["serial"].close()
                        logger.log_info(
                            f"Session {sid} ({session['port']}) auto-closed after "
                            f"{self._session_idle_timeout:.0f}s idle"
                        )
                    except Exception:
                        pass

    def _close_all_sessions(self) -> None:
        """关闭所有活跃会话（用于退出清理）。"""
        ids = []
        with self._session_lock:
            ids = list(self._sessions.keys())
            for sid in ids:
                if sid in self._sessions:
                    self._sessions[sid]["closing"] = True
        for sid in ids:
            with self._session_lock:
                session = self._sessions.pop(sid, None)
            if session:
                try:
                    session["serial"].close()
                except Exception:
                    pass

    # ======================== 硬件调试实现 ========================

    @staticmethod
    async def _serial_pin_status(port: str, baud_rate: int = 115200) -> dict:
        """读取串口信号线状态。"""
        ser = None
        try:
            ser = serial.Serial(port=port, baudrate=baud_rate, timeout=0.5)
            return {
                "success": True,
                "port": port,
                "pins": {
                    "cts": ser.cts,
                    "dsr": ser.dsr,
                    "dcd": ser.cd,
                    "ri": ser.ri,
                },
                "descriptions": {
                    "cts": "Clear To Send — 对方可以接收",
                    "dsr": "Data Set Ready — 设备就绪",
                    "dcd": "Data Carrier Detect — 载波检测",
                    "ri": "Ring Indicator — 振铃指示",
                },
            }
        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    @staticmethod
    async def _serial_pin_set(
        port: str,
        dtr: Optional[bool] = None,
        rts: Optional[bool] = None,
        baud_rate: int = 115200,
    ) -> dict:
        """设置串口 DTR/RTS 信号电平。"""
        ser = None
        try:
            ser = serial.Serial(port=port, baudrate=baud_rate, timeout=0.5)
            changes = {}
            if dtr is not None:
                ser.dtr = dtr
                changes["dtr"] = dtr
            if rts is not None:
                ser.rts = rts
                changes["rts"] = rts
            return {
                "success": True,
                "port": port,
                "changes": changes,
            }
        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    @staticmethod
    async def _serial_loopback_test(
        port: str,
        baud_rate: int = 115200,
        mode: str = "hardware",
        test_data: Optional[str] = None,
        probe_command: str = "AT",
        probe_expected: str = "OK",
        timeout: float = 3.0,
    ) -> dict:
        """串口回环测试。"""
        ser = None
        try:
            ser = serial.Serial(
                port=port, baudrate=baud_rate,
                timeout=timeout, write_timeout=timeout,
            )

            if mode == "hardware":
                payload = test_data or "AutoCom_Loopback_Test_0123456789"
                send_bytes = payload.encode("utf-8")
                start = time.perf_counter()
                ser.write(send_bytes)
                ser.flush()

                received = b""
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        chunk = ser.read(ser.in_waiting or 1)
                    except Exception:
                        break
                    if chunk:
                        received += chunk
                        if len(received) >= len(send_bytes):
                            break

                elapsed_ms = (time.perf_counter() - start) * 1000
                match = received == send_bytes
                match_ratio = (
                    sum(1 for a, b in zip(received, send_bytes) if a == b) / len(send_bytes)
                    if send_bytes else 0
                ) if not match else 1.0

                return {
                    "success": match,
                    "port": port,
                    "mode": "hardware",
                    "test_data_hex": send_bytes.hex(" "),
                    "received_hex": received.hex(" "),
                    "received_text": received.decode("utf-8", errors="replace"),
                    "match": match,
                    "match_ratio": round(match_ratio, 4),
                    "sent_bytes": len(send_bytes),
                    "received_bytes": len(received),
                    "elapsed_ms": round(elapsed_ms, 2),
                }

            elif mode == "echo":
                cmd_bytes = probe_command.encode("utf-8") + b"\r\n"
                start = time.perf_counter()
                ser.write(cmd_bytes)
                ser.flush()

                received = b""
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        chunk = ser.read(ser.in_waiting or 1)
                    except Exception:
                        break
                    if chunk:
                        received += chunk

                elapsed_ms = (time.perf_counter() - start) * 1000
                text = received.decode("utf-8", errors="replace")
                found = probe_expected in text

                return {
                    "success": found,
                    "port": port,
                    "mode": "echo",
                    "command": probe_command,
                    "expected": probe_expected,
                    "response": text,
                    "matched": found,
                    "elapsed_ms": round(elapsed_ms, 2),
                }
            else:
                return {"success": False, "error": f"Unknown mode: {mode}, options: hardware, echo"}

        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    @staticmethod
    async def _serial_latency_bench(
        port: str,
        baud_rate: int = 115200,
        rounds: int = 10,
        test_data: str = "AT",
        timeout: float = 5.0,
    ) -> dict:
        """串口收发延迟基准测试。"""
        ser = None
        try:
            ser = serial.Serial(
                port=port, baudrate=baud_rate,
                timeout=timeout, write_timeout=timeout,
            )

            send_bytes = test_data.encode("utf-8") + b"\r\n"
            tx_latencies = []
            rtt_latencies = []
            first_byte_latencies = []
            errors = 0

            for i in range(rounds):
                # TX 延迟：write() 返回耗时
                t0 = time.perf_counter()
                ser.write(send_bytes)
                ser.flush()
                tx_done = time.perf_counter()
                tx_lat = (tx_done - t0) * 1000

                # 等待并读取响应
                received = b""
                first_byte_time = None
                deadline = time.time() + timeout

                while time.time() < deadline:
                    try:
                        chunk = ser.read(ser.in_waiting or 1)
                    except Exception:
                        break
                    if chunk:
                        if first_byte_time is None:
                            first_byte_time = time.perf_counter()
                            fbl = (first_byte_time - t0) * 1000
                            first_byte_latencies.append(fbl)
                        received += chunk
                    else:
                        if received:
                            break

                rx_done = time.perf_counter()
                rtt = (rx_done - t0) * 1000

                if received:
                    tx_latencies.append(tx_lat)
                    rtt_latencies.append(rtt)
                else:
                    errors += 1

                # 间隔 50ms 避免数据残留
                if i < rounds - 1:
                    await asyncio.sleep(0.05)

            result = {
                "success": errors < rounds,
                "port": port,
                "baud_rate": baud_rate,
                "test_data": test_data,
                "rounds": rounds,
                "errors": errors,
            }

            if tx_latencies:
                result["tx_latency_ms"] = {
                    "min": round(min(tx_latencies), 3),
                    "max": round(max(tx_latencies), 3),
                    "avg": round(sum(tx_latencies) / len(tx_latencies), 3),
                }
            if first_byte_latencies:
                result["first_byte_latency_ms"] = {
                    "min": round(min(first_byte_latencies), 3),
                    "max": round(max(first_byte_latencies), 3),
                    "avg": round(sum(first_byte_latencies) / len(first_byte_latencies), 3),
                }
            if rtt_latencies:
                result["rtt_ms"] = {
                    "min": round(min(rtt_latencies), 3),
                    "max": round(max(rtt_latencies), 3),
                    "avg": round(sum(rtt_latencies) / len(rtt_latencies), 3),
                    "median": round(sorted(rtt_latencies)[len(rtt_latencies) // 2], 3),
                }
            if errors > 0:
                result["note"] = f"{errors}/{rounds} rounds got no response — device may not be connected or may not reply"

            return result

        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    # ======================== 流水线配置管理 ========================

    @staticmethod
    async def _pipeline_list(base_dir: Optional[str] = None) -> dict:
        """列出指定目录下所有可用的流水线配置文件。"""
        from pathlib import Path

        search_dirs = []
        if base_dir:
            search_dirs.append(Path(base_dir))
        else:
            for d in ("dicts", "configs"):
                p = Path(d)
                if p.is_dir():
                    search_dirs.append(p)

        pipelines = []
        seen = set()
        for sd in search_dirs:
            for ext in ("*.yaml", "*.yml", "*.json"):
                for f in sorted(sd.rglob(ext)):
                    if f.name.startswith("."):
                        continue
                    abspath = str(f.resolve())
                    if abspath in seen:
                        continue
                    seen.add(abspath)
                    try:
                        stat = f.stat()
                    except Exception:
                        stat = None
                    pipelines.append({
                        "file_path": abspath,
                        "file_name": f.name,
                        "relative_path": str(f.relative_to(Path.cwd())),
                        "size_bytes": stat.st_size if stat else 0,
                        "modified": stat.st_mtime if stat else 0,
                        "directory": str(f.parent),
                    })
        return {"success": True, "total": len(pipelines), "pipelines": pipelines}

    # ======================== 执行历史与分析 ========================

    @staticmethod
    async def _execution_list(limit: int = 20) -> dict:
        """列出最近的执行会话。"""
        from pathlib import Path

        base = Path("device_logs")
        if not base.is_dir():
            return {"success": True, "total": 0, "sessions": []}

        sessions = []
        for entry in sorted(base.iterdir(), key=lambda e: e.name, reverse=True):
            if not entry.is_dir():
                continue
            has_log = (entry / "EXECUTION.log").is_file()
            has_json = (entry / "EXECUTION.json").is_file()
            device_logs = sorted(f.name for f in entry.iterdir()
                                 if f.suffix == ".log" and f.name != "EXECUTION.log")
            sessions.append({
                "session_id": entry.name,
                "path": str(entry.resolve()),
                "has_log": has_log,
                "has_json": has_json,
                "device_logs": device_logs,
                "device_count": len(device_logs),
            })
            if len(sessions) >= limit:
                break

        return {"success": True, "total": len(sessions), "sessions": sessions}

    @staticmethod
    async def _execution_report(session_id: str) -> dict:
        """解析指定执行会话的日志和结果。"""
        from pathlib import Path

        session_dir = Path("device_logs") / session_id
        if not session_dir.is_dir():
            return {"success": False, "error": f"Session '{session_id}' not found in device_logs/"}

        result = {
            "success": True,
            "session_id": session_id,
            "path": str(session_dir.resolve()),
            "execution_log": None,
            "device_logs": {},
            "summary": {},
        }

        # 读取 EXECUTION.log
        exec_log = session_dir / "EXECUTION.log"
        if exec_log.is_file():
            try:
                lines = exec_log.read_text("utf-8", errors="replace").splitlines()
                result["execution_log"] = {
                    "line_count": len(lines),
                    "content": lines[:500],  # 限制返回行数
                    "truncated": len(lines) > 500,
                }
                # 提取摘要
                summary = {"iterations": 0, "passed": 0, "failed": 0, "errors": [], "total_time": ""}
                for line in lines:
                    if "iteration" in line.lower() and "failed" in line.lower():
                        summary["failed"] += 1
                    if "iteration" in line.lower() and "pass" in line.lower():
                        summary["passed"] += 1
                    if "Summary:" in line:
                        summary["iterations"] = summary.get("iterations", 0) + 1
                    if "Total execution time" in line:
                        summary["total_time"] = line
                    if "ERROR" in line or "FATAL" in line:
                        summary["errors"].append(line)
                result["summary"] = summary
            except Exception as e:
                result["execution_log"] = {"error": str(e)}

        # 读取设备日志
        for f in sorted(session_dir.iterdir()):
            if f.suffix == ".log" and f.name != "EXECUTION.log":
                try:
                    dev_lines = f.read_text("utf-8", errors="replace").splitlines()
                    result["device_logs"][f.name] = {
                        "line_count": len(dev_lines),
                        "content": dev_lines[:200],
                        "truncated": len(dev_lines) > 200,
                    }
                except Exception as e:
                    result["device_logs"][f.name] = {"error": str(e)}

        return result

    @staticmethod
    async def _session_log_query(session_id: str, keyword: str, max_results: int = 50) -> dict:
        """在指定会话的日志中搜索关键词。"""
        from pathlib import Path

        session_dir = Path("device_logs") / session_id
        if not session_dir.is_dir():
            return {"success": False, "error": f"Session '{session_id}' not found"}

        matches = []
        for f in sorted(session_dir.iterdir()):
            if f.suffix != ".log":
                continue
            try:
                for lineno, line in enumerate(f.read_text("utf-8", errors="replace").splitlines(), 1):
                    if keyword.lower() in line.lower():
                        matches.append({
                            "file": f.name,
                            "line": lineno,
                            "text": line.strip(),
                        })
                        if len(matches) >= max_results:
                            break
            except Exception:
                pass
            if len(matches) >= max_results:
                break

        return {
            "success": True,
            "session_id": session_id,
            "keyword": keyword,
            "total_matches": len(matches),
            "matches": matches,
        }

    # ======================== 串口调试增强 ========================

    BAUD_RATES_TO_TRY = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

    @staticmethod
    async def _serial_baud_scan(port: str, test_command: str = "AT", expected_response: str = "OK",
                                 line_ending: str = "0d0a") -> dict:
        """自动尝试常用波特率，找到能收到期望响应的那个。"""
        import serial

        line_ending_bytes = bytes.fromhex(line_ending) if line_ending else b"\r\n"
        cmd = (test_command or "AT").strip() or "AT"
        send_data = cmd.encode("utf-8") + line_ending_bytes

        results = []
        for baud in AutoComMCPServer.BAUD_RATES_TO_TRY:
            ser = None
            t0 = time.time()
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.2,
                )
                time.sleep(0.15)  # wait for port to settle
                ser.reset_input_buffer()  # clear stale data
                ser.write(send_data)

                # 轮询读取（同 execute_serial_command 策略）
                resp = b""
                deadline = time.time() + 1.0
                while time.time() < deadline:
                    if ser.in_waiting:
                        chunk = ser.read(ser.in_waiting)
                        resp += chunk
                        # 如果已经收到期望内容，提前退出
                        if expected_response.encode("utf-8") in resp:
                            break
                    await asyncio.sleep(0.02)

                text = resp.decode("utf-8", errors="replace")
                elapsed = round((time.time() - t0) * 1000, 1)
                matched = expected_response in text
                results.append({
                    "baud_rate": baud,
                    "success": matched,
                    "response": text.strip() if text else "(no response)",
                    "elapsed_ms": elapsed,
                })
            except Exception as e:
                results.append({
                    "baud_rate": baud,
                    "success": False,
                    "error": str(e),
                })
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

        working = [r for r in results if r.get("success")]
        return {
            "success": True,
            "port": port,
            "test_command": test_command,
            "expected_response": expected_response,
            "total_tried": len(results),
            "working_count": len(working),
            "working_rates": [r["baud_rate"] for r in working],
            "results": results,
        }

    @staticmethod
    async def _serial_hex_dump(port: str, baud_rate: int = 115200, bytes_to_read: int = 256,
                                timeout: float = 3.0) -> dict:
        """以 hex + ASCII 格式读取串口数据，排查乱码问题。"""
        import serial

        ser = None
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
            )
            raw = ser.read(bytes_to_read)
            if not raw:
                return {"success": True, "port": port, "baud_rate": baud_rate,
                        "bytes_read": 0, "hex_dump": [], "text": "(no data)"}

            # 格式化 hex dump
            hex_lines = []
            for i in range(0, len(raw), 16):
                chunk = raw[i:i + 16]
                hex_part = " ".join(f"{b:02x}" for b in chunk)
                # 补齐空格
                hex_part = hex_part.ljust(16 * 3 - 1)
                ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                hex_lines.append(f"{i:08x}  {hex_part}  |{ascii_part}|")

            return {
                "success": True,
                "port": port,
                "baud_rate": baud_rate,
                "bytes_read": len(raw),
                "hex_dump": hex_lines,
                "text": raw.decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {"success": False, "port": port, "error": str(e)}
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    # ======================== 设备参数管理 ========================

    @staticmethod
    def _profiles_path() -> Path:
        return Path("data") / "device_profiles.json"

    @staticmethod
    async def _device_profile_list() -> dict:
        """列出所有已保存的设备配置。"""
        profiles_path = AutoComMCPServer._profiles_path()
        if not profiles_path.is_file():
            return {"success": True, "total": 0, "profiles": []}
        try:
            profiles = json.loads(profiles_path.read_text("utf-8"))
            if not isinstance(profiles, list):
                profiles = []
            return {"success": True, "total": len(profiles), "profiles": profiles}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    async def _device_profile_save(name: str, port: str, baud_rate: int = 115200,
                                    data_bits: int = 8, stop_bits: int = 1,
                                    parity: str = "none", flow_control: bool = False,
                                    timeout: float = 5.0, label: str = "") -> dict:
        """保存设备配置。"""
        profile = {
            "name": name,
            "port": port,
            "baud_rate": baud_rate,
            "data_bits": data_bits,
            "stop_bits": stop_bits,
            "parity": parity,
            "flow_control": flow_control,
            "timeout": timeout,
            "label": label or name,
            "created": time.time(),
        }

        profiles_path = AutoComMCPServer._profiles_path()
        profiles_path.parent.mkdir(parents=True, exist_ok=True)

        profiles = []
        if profiles_path.is_file():
            try:
                profiles = json.loads(profiles_path.read_text("utf-8"))
            except Exception:
                profiles = []

        # 同名更新
        for i, p in enumerate(profiles):
            if p.get("name") == name:
                profile["created"] = p.get("created", time.time())
                profiles[i] = profile
                break
        else:
            profiles.append(profile)

        profiles_path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), "utf-8")
        return {"success": True, "profile": profile, "total": len(profiles)}

    @staticmethod
    async def _device_profile_delete(name: str) -> dict:
        """删除已保存的设备配置。"""
        profiles_path = AutoComMCPServer._profiles_path()
        if not profiles_path.is_file():
            return {"success": False, "error": f"Profile '{name}' not found"}

        try:
            profiles = json.loads(profiles_path.read_text("utf-8"))
            before = len(profiles)
            profiles = [p for p in profiles if p.get("name") != name]
            if len(profiles) == before:
                return {"success": False, "error": f"Profile '{name}' not found"}
            profiles_path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), "utf-8")
            return {"success": True, "deleted": name, "total": len(profiles)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ======================== 单步调试 ========================

    @staticmethod
    async def _pipeline_step_debug(file_path: str, step_id: str,
                                    config_overrides: Optional[dict] = None) -> dict:
        """只执行流水线中的某一个步骤，方便单独调试。"""
        from components.PipelineScheduler import PipelineScheduler
        from pathlib import Path

        fpath = Path(file_path)
        if not fpath.is_file():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            # 加载配置
            import yaml
            raw = fpath.read_text("utf-8")
            data = yaml.safe_load(raw)
            if not isinstance(data, dict):
                return {"success": False, "error": "Config root must be an object"}

            # 应用覆盖
            if config_overrides:
                from copy import deepcopy
                data = deepcopy(data)
                for key, val in config_overrides.items():
                    data[key] = val

            # 找到目标步骤
            steps = data.get("Steps", [])
            target_step = None
            for s in steps:
                if s.get("id") == step_id:
                    target_step = s
                    break
            if target_step is None:
                return {"success": False, "error": f"Step '{step_id}' not found in Steps"}

            # 构建临时 PipelineScheduler 并执行单步
            scheduler = PipelineScheduler(data)
            result = await scheduler.execute_single_step(target_step)
            return {
                "success": True,
                "file_path": file_path,
                "step_id": step_id,
                "step_type": target_step.get("type"),
                "result": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    async def _pipeline_dry_run(file_path: str, config_overrides: Optional[dict] = None) -> dict:
        """对流水线做干运行：解析变量、追踪控制流，但不执行实际 I/O。"""
        from pathlib import Path

        fpath = Path(file_path)
        if not fpath.is_file():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            import yaml
            raw = fpath.read_text("utf-8")
            data = yaml.safe_load(raw)
            if not isinstance(data, dict):
                return {"success": False, "error": "Config root must be an object"}

            if config_overrides:
                from copy import deepcopy
                data = deepcopy(data)
                for key, val in config_overrides.items():
                    data[key] = val

            devices = data.get("Devices", [])
            steps = data.get("Steps", [])
            constants = data.get("Constants", {})
            config_block = data.get("Config", {})
            loop_shorthand = data.get("loop")

            # 解析执行模式
            mode = "single"
            iterations = 1
            if isinstance(config_block, dict):
                mode = config_block.get("mode", "single")
                loop_cfg = config_block.get("loop", {})
                if isinstance(loop_cfg, dict):
                    iterations = loop_cfg.get("iterations", 1)
            if loop_shorthand is not None:
                mode = "loop"
                iterations = loop_shorthand if isinstance(loop_shorthand, int) else 1

            # 步骤列表
            step_analysis = []
            for s in steps:
                sid = s.get("id", "?")
                stype = s.get("type", "?")
                deps = []
                # 检查变量引用
                for field in ("send", "command", "url"):
                    val = s.get(field, "")
                    if isinstance(val, str):
                        import re
                        for m in re.finditer(r"\{([A-Za-z_]\w*)\}", val):
                            k = m.group(1)
                            if k not in constants:
                                deps.append(f"undefined constant: {{{k}}}")
                        for m in re.finditer(r"\{\{\s*steps\.(\w+)\.capture\.(\w+)\s*\}\}", val):
                            sid_ref = m.group(1)
                            if sid_ref not in {x.get("id") for x in steps}:
                                deps.append(f"undefined step ref: {sid_ref}")

                step_analysis.append({
                    "id": sid,
                    "type": stype,
                    "device": s.get("device", ""),
                    "has_expect": "expect" in s,
                    "has_capture": "capture" in s,
                    "timeout": s.get("timeout"),
                    "on_error": s.get("on_error"),
                    "on_success": s.get("on_success"),
                    "condition": s.get("if") or s.get("unless"),
                    "issues": deps,
                })

            # 控制流追踪
            flow_trace = []
            ids = {s["id"] for s in step_analysis}
            for s in step_analysis:
                if s["type"] == "goto":
                    target = None
                    for st in steps:
                        if st.get("id") == s["id"]:
                            target = st.get("target")
                    if target and target not in ids:
                        flow_trace.append(f"goto '{s['id']}' -> target '{target}' not found")
                    elif target:
                        flow_trace.append(f"goto '{s['id']}' -> '{target}'")
                on_err = s.get("on_error", "")
                if isinstance(on_err, str) and "goto(" in on_err:
                    import re
                    m = re.search(r"goto\((.+?)\)", on_err)
                    if m and m.group(1) not in ids:
                        flow_trace.append(f"on_error goto in '{s['id']}' -> '{m.group(1)}' not found")

            return {
                "success": True,
                "file_path": file_path,
                "config": {
                    "mode": mode,
                    "iterations": iterations,
                },
                "devices": [{"name": d.get("name"), "port": d.get("port")} for d in devices if isinstance(d, dict)],
                "constants": list(constants.keys()) if isinstance(constants, dict) else [],
                "steps": step_analysis,
                "flow_issues": flow_trace,
                "total_steps": len(steps),
                "has_issues": len(flow_trace) > 0 or any(s["issues"] for s in step_analysis),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


def _create_auth_middleware(auth_key: str):
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class AuthMiddleware(BaseHTTPMiddleware):
        def __init__(self, app):
            super().__init__(app)
            self.auth_key = auth_key

        async def dispatch(self, request, call_next):
            if request.method == "OPTIONS":
                return await call_next(request)
            if request.url.path in ("/health", "/"):
                return await call_next(request)

            auth_header = request.headers.get("authorization", "")
            api_key_header = request.headers.get("x-api-key", "")

            token = None
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:]
            elif api_key_header:
                token = api_key_header

            if token != auth_key:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await call_next(request)

    return AuthMiddleware


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AutoCom MCP Server (FastMCP)")
    transport_group = parser.add_mutually_exclusive_group()
    transport_group.add_argument("--sse", action="store_true", help="以 SSE (HTTP) 模式运行")
    transport_group.add_argument("--streamable", action="store_true", help="以 Streamable HTTP 模式运行（长连接/双向通道）")
    parser.add_argument("--auth-key", type=str, default=None, help="为 HTTP 模式启用简单 API Key 鉴权")
    parser.add_argument("--port", type=int, default=8888, help="HTTP 模式监听端口（默认 8888）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="HTTP 模式监听地址（默认 0.0.0.0）")
    args = parser.parse_args()

    if not _FASTMCP_AVAILABLE:
        print("Error: fastmcp 未安装。请运行: pip install fastmcp")
        raise SystemExit(1)

    server = AutoComMCPServer(auth_key=args.auth_key)

    def _run_mcp_callable(obj, name: str, /, *a, **kw):
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

    def _safe_stderr_message(message: str) -> None:
        try:
            sys.stderr.write(message + "\n")
            sys.stderr.flush()
        except Exception:
            pass

    def _invoke_stdio_method(mcp_obj, auth_key=None):
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
                        on_interrupt=lambda: _safe_stderr_message("MCP Server received interrupt signal, shutting down..."),
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
            f"No compatible stdio method found among {candidates}.\n"
            f"Available attributes: {available}"
        )
        print(msg)
        logger.log_error(msg)
        raise SystemExit(1)

    # HTTP 备选方法名列表
    _HTTP_METHOD_CANDIDATES = {
        "sse": ["run_sse_async", "run_http_async"],
        "streamable-http": ["run_streamable_async", "run_http_async"],
    }

    try:
        if args.sse:
            transport = "sse"
            path = "/mcp/sse"
            http_candidates = _HTTP_METHOD_CANDIDATES["sse"]
        elif args.streamable:
            transport = "streamable-http"
            path = "/mcp/stream"
            http_candidates = _HTTP_METHOD_CANDIDATES["streamable-http"]
        else:
            # stdio 模式
            try:
                _invoke_stdio_method(server.mcp, auth_key=args.auth_key)
            except (KeyboardInterrupt, asyncio.CancelledError):
                _safe_stderr_message("MCP Server received interrupt signal, shutting down...")
            finally:
                server._close_all_sessions()
            return

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

        # 按优先级尝试 HTTP 运行方法
        http_method_name = None
        for candidate in http_candidates:
            if hasattr(server.mcp, candidate):
                http_method_name = candidate
                break

        if http_method_name is None:
            available = [n for n in dir(server.mcp) if not n.startswith("_")]
            msg = (
                f"No compatible HTTP method found for '{transport}' mode.\n"
                f"Searched: {http_candidates}\n"
                f"Available attributes: {available}"
            )
            print(msg)
            logger.log_error(msg)
            raise SystemExit(1)

        reachable = _get_reachable_host(args.host)
        logger.log_info(f"Starting {transport} server: http://{reachable}:{args.port}{path}")
        if args.host == "0.0.0.0":
            logger.log_info(f"LAN: http://{reachable}:{args.port}{path}  |  Local: http://127.0.0.1:{args.port}{path}")
        logger.log_info(f"Audit log directory: {server.audit_log_path}")
        _run_mcp_callable(
            server.mcp,
            http_method_name,
            host=args.host,
            port=args.port,
            path=path,
            middleware=middleware,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        _safe_stderr_message("MCP Server received interrupt signal, shutting down...")
    finally:
        server._close_all_sessions()


if __name__ == "__main__":
    main()