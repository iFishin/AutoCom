#!/usr/bin/env python3
"""
AutoCom REST API Server — 基于 FastAPI 的 HTTP REST 接口。

提供与 MCP 工具集对齐的全功能 REST API，包括串口操作、硬件诊断、
流水线执行、执行历史、设备配置管理等。

启动方式: autocom api --port 8000 --host 0.0.0.0
Swagger UI: http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI, Body, HTTPException, Response, WebSocket, WebSocketDisconnect, Query
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn

try:
    from fastapi import FastAPI, Body, HTTPException, Response, WebSocket, WebSocketDisconnect, Query
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn

    _FASTAPI_AVAILABLE = True

    # ── 响应模型 ──

    class SessionOpenResponse(BaseModel):
        success: bool
        session_id: str | None = None
        port: str | None = None
        baud_rate: int | None = None
        label: str | None = None

    class SessionListItem(BaseModel):
        session_id: str | None = None
        port: str
        baud_rate: int
        label: str
        created_at: float
        idle_seconds: float

    class SessionListResponse(BaseModel):
        success: bool
        sessions: list[SessionListItem]
        total: int

    class SessionDetailResponse(BaseModel):
        success: bool
        session_id: str | None = None
        port: str
        baud_rate: int
        label: str
        created_at: float

    class SessionCloseResponse(BaseModel):
        success: bool
        session_id: str | None = None

    class SessionSendResponse(BaseModel):
        success: bool
        command: str
        response: str
        elapsed_ms: int
        bytes: int

    class SessionReadResponse(BaseModel):
        success: bool
        data: str
        bytes_count: int
        session_id: str | None = None

    # ── 串口操作响应模型 ──

    class HealthResponse(BaseModel):
        status: str
        version: str
        sessions: int

    class PingResponse(BaseModel):
        pong: bool

    class SystemInfoResponse(BaseModel):
        success: bool
        hostname: str
        ip: str
        version: str
        python_version: str
        platform: str
        pid: int
        uptime_seconds: float
        active_sessions: int

    class StatsResponse(BaseModel):
        success: bool
        uptime_seconds: float
        active_sessions: int
        started_at: float

    class PortItem(BaseModel):
        device: str
        description: str
        hwid: str
        vid: int | None = None
        pid: int | None = None
        serial_number: str | None = None
        manufacturer: str | None = None

    class PortListResponse(BaseModel):
        success: bool
        total: int
        devices: list[PortItem]

    class CommandResponse(BaseModel):
        success: bool
        port: str
        command: str | None = None
        response: str | None = None
        elapsed_ms: int | None = None
        error: str | None = None

    class BaudRateResult(BaseModel):
        baud_rate: int
        response: str | None = None
        elapsed_ms: float = 0
        elapsed_ms: float
        error: str | None = None

    class BaudScanResponse(BaseModel):
        success: bool
        port: str
        test_command: str
        expected_response: str
        total_tried: int
        working_count: int
        working_rates: list[int]
        results: list[BaudRateResult]

    class HexDumpLine(BaseModel):
        offset: int
        hex: str
        ascii: str
        raw: list[int]

    class HexDumpResponse(BaseModel):
        success: bool
        port: str
        baud_rate: int | None = None
        bytes_read: int = 0
        hex_dump: list = []
        raw_bytes: list = []
        text: str = ""

    class PinStatusResponse(BaseModel):
        success: bool
        port: str
        cts: bool | None = None
        dsr: bool | None = None
        dcd: bool | None = None
        ri: bool | None = None
        error: str | None = None

    class PinSetResponse(BaseModel):
        success: bool
        port: str
        error: str | None = None

    class LoopbackResponse(BaseModel):
        success: bool
        port: str
        mode: str
        sent_bytes: int
        received_bytes: int
        elapsed_ms: float
        error: str | None = None

    class LatencyStats(BaseModel):
        min: float
        max: float
        avg: float

    class LatencyResponse(BaseModel):
        success: bool
        port: str
        baud_rate: int
        test_data: str
        rounds: int
        errors: int
        tx_latency_ms: LatencyStats | None = None
        first_byte_latency_ms: LatencyStats | None = None
        rtt_ms: LatencyStats | None = None

    # ── 流水线 / 执行历史响应模型 ──

    class PipelineStepBrief(BaseModel):
        id: str
        type: str
        device: str | None = None
        has_expect: bool = False
        has_capture: bool = False
        timeout: int | None = None
        on_error: str | None = None
        on_success: str | None = None
        condition: str | None = None
        issues: list[str] = []

    class PipelineItem(BaseModel):
        name: str
        # path removed for security
        size_bytes: int
        modified: float

    class PipelineListResponse(BaseModel):
        success: bool
        total: int
        pipelines: list[PipelineItem]

    class PipelineSaveRequest(BaseModel):
        content: str

    class PipelineSaveResponse(BaseModel):
        success: bool
        name: str


    class PipelineDeleteResponse(BaseModel):
        success: bool
        name: str

    class PipelineContentResponse(BaseModel):
        success: bool
        name: str
        content: str
        size_bytes: int
    class PipelineListResponse(BaseModel):
        success: bool
        total: int
        pipelines: list[PipelineItem]

    class PipelineDryRunResponse(BaseModel):
        success: bool
        file_path: str
        config: dict | None = None
        devices: list[dict] = []
        constants: list[str] = []
        steps: list[PipelineStepBrief] = []
        flow_issues: list[str] = []
        total_steps: int = 0
        has_issues: bool = False

    class StepDebugResult(BaseModel):
        step_id: str
        step_type: str
        passed: bool
        output: str | None = None
        captures: dict = {}
        error: str | None = None
        execution_time_ms: float = 0
        skipped: bool = False

    class PipelineStepDebugResponse(BaseModel):
        success: bool
        file_path: str
        step_id: str
        step_type: str | None = None
        result: StepDebugResult | None = None

    class PipelineValidateResponse(BaseModel):
        success: bool
        errors: list[dict] = []
        warnings: list[dict] = []
        summary: str | None = None

    class PipelineRunResponse(BaseModel):
        success: bool
        session_id: str | None = None
        executed_iterations: int = 0
        mode: str = ""
        elapsed_seconds: float = 0
        results: list[dict] = []

    class ExecutionSession(BaseModel):
        type: str = "pipeline"
        session_id: str | None = None
        has_log: bool = False
        has_json: bool = False
        device_logs: list[str] = []
        device_count: int = 0
        log_count: int = 0
        config_count: int = 0
        line_count: int = 0

    class ExecutionListResponse(BaseModel):
        success: bool
        total: int
        sessions: list[ExecutionSession]

    class ExecutionReportResponse(BaseModel):
        success: bool
        session_id: str | None = None
        execution_log: dict | None = None
        device_logs: list[dict] = []
        summary: dict = {}
        step_results: list[dict] = []

    class LogMatch(BaseModel):
        session_id: str | None = None
        file: str
        line: int
        text: str
    class LogSearchResponse(BaseModel):
        success: bool
        keyword: str = ""
        total_matches: int = 0
        matches: list[LogMatch] = []

    # ── 设备配置响应模型 ──

    class ProfileItem(BaseModel):
        name: str
        port: str
        baud_rate: int
        data_bits: int
        stop_bits: int
        parity: str
        flow_control: bool
        timeout: float
        label: str
        created: float

    class ProfileListResponse(BaseModel):
        success: bool
        total: int
        profiles: list[ProfileItem]

    class ProfileSaveResponse(BaseModel):
        success: bool
        profile: ProfileItem
        total: int

    class ProfileDeleteResponse(BaseModel):
        success: bool
        deleted: str
        total: int

except Exception:
    _FASTAPI_AVAILABLE = False


# 复用 MCPServer 的串口操作方法
from components.MCPServer import AutoComMCPServer
from components.Logger import AutoComLogger, get_logger
from utils.serial_helpers import parse_line_ending as _parse_le
from version import __version__

logger: AutoComLogger = get_logger("AutoCom.API")


class AutoComRESTServer:
    """AutoCom REST API Server — 基于 FastAPI。"""

    session_idle_timeout: float = 300.0  # 5 分钟无操作自动关闭
    session_cleanup_interval: float = 30.0

    def __init__(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        self.host = host
        self.port = port
        self._started_at = time.time()

        self.app = FastAPI(
            title="AutoCom REST API",
            version=__version__,
            description="AutoCom 串口调试与流水线执行 REST API",
            docs_url="/docs",
            redoc_url="/redoc",
        )

        # CORS — 允许任意来源（开发阶段）
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 独立会话管理（与 MCP 不共享）
        self._sessions: dict[str, dict[str, Any]] = {}
        self._session_lock = threading.Lock()

        # 后台会话清理
        self._cleanup_thread = threading.Thread(
            target=self._session_cleanup_worker, daemon=True
        )
        self._cleanup_thread.start()

        # 注册路由
        self._register_routes()

    # ── 路由注册 ──

    def _register_routes(self) -> None:
        app = self.app

        # ─── 健康检查 ───

        @app.get("/api/health", tags=["系统"], response_model=HealthResponse)
        async def health() -> dict:
            """健康检查，返回服务状态和版本号"""
            return {
                "status": "ok",
                "version": __version__,
                "sessions": len(self._sessions),
            }

        @app.get("/api/ping", tags=["系统"], response_model=PingResponse)
        async def ping() -> dict:
            """连通性检测"""
            return {"pong": True}

        @app.get("/api/system/info", tags=["系统"], response_model=SystemInfoResponse)
        async def system_info() -> dict:
            """查询系统信息：主机名、IP、版本等"""
            import socket
            hostname = socket.gethostname()
            ip = "127.0.0.1"
            try:
                for addr in socket.getaddrinfo(hostname, None):
                    if addr[0] == socket.AF_INET:
                        ip_candidate = addr[4][0]
                        if not ip_candidate.startswith("127."):
                            ip = ip_candidate
                            break
            except Exception:
                pass
            return {
                "success": True,
                "hostname": hostname,
                "ip": ip,
                "version": __version__,
                "python_version": __import__("sys").version,
                "platform": __import__("sys").platform,
                "pid": __import__("os").getpid(),
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "active_sessions": len(self._sessions),
            }

        @app.get("/api/stats", tags=["系统"], response_model=StatsResponse)
        async def stats() -> dict:
            """API 运行时统计"""
            return {
                "success": True,
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "active_sessions": len(self._sessions),
                "started_at": self._started_at,
            }

        # ─── 串口基础操作 ───

        @app.get("/api/ports", tags=["串口操作"], response_model=PortListResponse)
        async def list_ports() -> dict:
            """列出当前可用的串口设备"""
            return await AutoComMCPServer._list_serial_ports()

        @app.post("/api/ports/{port}/command", tags=["串口操作"], response_model=CommandResponse)
        async def execute_command(
            port: str,
            command: str = Query(..., description="要发送的指令"),
            baud_rate: int = Query(115200, description="波特率"),
            timeout: float = Query(5.0, description="响应超时（秒）"),
            line_ending: str = Query("0d0a", description="行结尾的十六进制字节"),
            hex_mode: bool = Query(False, description="以十六进制字节发送"),
        ) -> dict:
            """向串口设备发送单条指令"""
            result = await AutoComMCPServer._execute_serial_command(
                port=port,
                command=command,
                baud_rate=baud_rate,
                timeout=timeout,
                line_ending=line_ending,
                hex_mode=hex_mode,
            )
            AutoComMCPServer._append_io_log("CMD", port, command,
                                            result.get("response", ""),
                                            success=result.get("success", False))
            return result

        @app.post("/api/ports/{port}/baud-scan", tags=["串口操作"], response_model=BaudScanResponse)
        async def baud_scan(
            port: str,
            body: dict = Body(default={"test_command": "AT", "expected_response": "OK", "line_ending": "0d0a"}),
        ) -> dict:
            """自动尝试常用波特率，找到能收到期望响应的那个"""
            cmd = (body.get("test_command") or "AT").strip() or "AT"
            expected = (body.get("expected_response") or "OK").strip() or "OK"
            line_end = body.get("line_ending", "0d0a") or "0d0a"
            return await AutoComMCPServer._serial_baud_scan(
                port=port,
                test_command=cmd,
                expected_response=expected,
                line_ending=line_end,
            )

        @app.get("/api/ports/{port}/hex-dump", tags=["串口操作"], response_model=HexDumpResponse)
        async def hex_dump(
            port: str,
            baud_rate: int = Query(115200, description="波特率"),
            bytes_to_read: int = Query(256, description="读取字节数"),
            timeout: float = Query(3.0, description="等待超时（秒）"),
        ) -> dict:
            """以 hex + ASCII 格式读取串口数据"""
            return await AutoComMCPServer._serial_hex_dump(
                port=port,
                baud_rate=baud_rate,
                bytes_to_read=bytes_to_read,
                timeout=timeout,
            )

        @app.get("/api/ports/{port}/pin-status", tags=["串口操作"], response_model=PinStatusResponse)
        async def pin_status(
            port: str,
            baud_rate: int = Query(115200, description="波特率"),
        ) -> dict:
            """读取串口信号线状态（CTS/DSR/DCD/RI）"""
            return await AutoComMCPServer._serial_pin_status(
                port=port, baud_rate=baud_rate
            )

        @app.post("/api/ports/{port}/pin-set", tags=["串口操作"], response_model=PinSetResponse)
        async def pin_set(
            port: str,
            baud_rate: int = Query(115200, description="波特率"),
            dtr: Optional[bool] = Query(None, description="DTR 输出电平"),
            rts: Optional[bool] = Query(None, description="RTS 输出电平"),
        ) -> dict:
            """设置 DTR/RTS 输出电平"""
            return await AutoComMCPServer._serial_pin_set(
                port=port, baud_rate=baud_rate, dtr=dtr, rts=rts
            )

        @app.post("/api/ports/{port}/loopback", tags=["串口操作"], response_model=LoopbackResponse)
        async def loopback_test(
            port: str,
            mode: str = Query("hardware", description="回环模式: hardware 或 echo"),
            baud_rate: int = Query(115200, description="波特率"),
            test_data: Optional[str] = Query(None, description="硬件回环测试数据"),
            probe_command: str = Query("AT", description="回声测试指令"),
            probe_expected: str = Query("OK", description="期望的回声响应"),
            timeout: float = Query(3.0, description="等待超时（秒）"),
        ) -> dict:
            """串口回环测试"""
            return await AutoComMCPServer._serial_loopback_test(
                port=port,
                mode=mode,
                baud_rate=baud_rate,
                test_data=test_data,
                probe_command=probe_command,
                probe_expected=probe_expected,
                timeout=timeout,
            )

        @app.post("/api/ports/{port}/latency", tags=["串口操作"], response_model=LatencyResponse)
        async def latency_bench(
            port: str,
            baud_rate: int = Query(115200, description="波特率"),
            rounds: int = Query(10, description="测试轮数"),
            test_data: str = Query("AT", description="每轮发送的数据"),
            timeout: float = Query(5.0, description="每轮超时（秒）"),
        ) -> dict:
            """串口收发延迟基准测试"""
            return await AutoComMCPServer._serial_latency_bench(
                port=port,
                baud_rate=baud_rate,
                rounds=rounds,
                test_data=test_data,
                timeout=timeout,
            )

        # ─── 串口监视 (WebSocket) ───

        @app.websocket("/api/ports/{port}/monitor")
        async def monitor_port(websocket: WebSocket, port: str, baud_rate: int = 115200):
            """实时监视串口输出（WebSocket）"""
            await websocket.accept()
            import serial

            ser: Optional[serial.Serial] = None
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.5,
                )
                await websocket.send_json({
                    "type": "connected",
                    "port": port,
                    "baud_rate": baud_rate,
                })

                while True:
                    try:
                        data = ser.read(256)
                        if data:
                            await websocket.send_json({
                                "type": "data",
                                "text": data.decode("utf-8", errors="replace"),
                                "hex": data.hex(),
                                "bytes": len(data),
                            })
                        else:
                            await asyncio.sleep(0.05)
                    except WebSocketDisconnect:
                        break
            except serial.SerialException as e:
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Serial error: {e}",
                    })
                except Exception:
                    pass
            except Exception as e:
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e),
                    })
                except Exception:
                    pass
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass
                try:
                    await websocket.close()
                except Exception:
                    pass

        # ─── 持久会话 ───

        @app.post("/api/sessions", tags=["持久会话"], response_model=SessionOpenResponse)
        async def open_session(
            port: str = Query(..., description="COM 端口名称"),
            baud_rate: int = Query(115200, description="波特率"),
            timeout: float = Query(5.0, description="读取超时（秒）"),
            label: Optional[str] = Query(None, description="会话标签"),
        ) -> dict:
            """打开一个持久串口会话"""
            import serial

            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            ser: Optional[serial.Serial] = None
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=timeout,
                )
            except serial.SerialException as e:
                return {"success": False, "error": f"Failed to open {port}: {e}"}

            session: dict[str, Any] = {
                "session_id": session_id,
                "port": port,
                "baud_rate": baud_rate,
                "label": label or f"{port}@{baud_rate}",
                "ser": ser,
                "created_at": time.time(),
                "last_active": time.time(),
            }

            with self._session_lock:
                self._sessions[session_id] = session

            return {
                "success": True,
                "session_id": session_id,
                "port": port,
                "baud_rate": baud_rate,
                "label": session["label"],
            }

        @app.get("/api/sessions", tags=["持久会话"], response_model=SessionListResponse)
        async def list_sessions() -> dict:
            """列出所有活跃的持久会话"""
            sessions: list[dict[str, Any]] = []
            now = time.time()
            with self._session_lock:
                for sid, sess in self._sessions.items():
                    sessions.append({
                        "session_id": sid,
                        "port": sess["port"],
                        "baud_rate": sess["baud_rate"],
                        "label": sess.get("label", ""),
                        "created_at": sess.get("created_at", 0),
                        "idle_seconds": round(now - sess.get("last_active", now), 1),
                    })
            return {"success": True, "sessions": sessions, "total": len(sessions)}

        @app.get("/api/sessions/{session_id}", tags=["持久会话"], response_model=SessionDetailResponse)
        async def get_session(session_id: str) -> dict:
            """获取单个会话的详细信息"""
            with self._session_lock:
                sess = self._sessions.get(session_id)
                if not sess:
                    raise HTTPException(status_code=404, detail="Session not found")
                return {
                    "success": True,
                    "session_id": session_id,
                    "port": sess["port"],
                    "baud_rate": sess["baud_rate"],
                    "label": sess.get("label", ""),
                    "created_at": sess.get("created_at", 0),
                }

        @app.delete("/api/sessions/{session_id}", tags=["持久会话"], response_model=SessionCloseResponse)
        async def close_session(session_id: str) -> dict:
            """关闭并清理持久会话"""
            with self._session_lock:
                sess = self._sessions.pop(session_id, None)
            if not sess:
                raise HTTPException(status_code=404, detail="Session not found")
            ser = sess.get("ser")
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            return {"success": True, "session_id": session_id}

        @app.post("/api/sessions/{session_id}/send", tags=["持久会话"], response_model=SessionSendResponse)
        async def session_send(
            session_id: str,
            command: str = Query(..., description="要发送的指令"),
            timeout: Optional[float] = Query(None, description="响应等待超时（秒）"),
            line_ending: str = Query("0d0a", description="行结尾的十六进制字节"),
        ) -> dict:
            """在持久会话中发送指令"""
            with self._session_lock:
                sess = self._sessions.get(session_id)
            if not sess:
                raise HTTPException(status_code=404, detail="Session not found")

            ser: Any = sess.get("ser")
            if ser is None:
                raise HTTPException(status_code=500, detail="Session serial handle is closed")

            line_ending_bytes = _parse_le(line_ending)
            send_bytes = command.encode("utf-8") + line_ending_bytes

            t0 = time.time()
            try:
                ser.write(send_bytes)
                ser.flush()
                resp = b""
                deadline = time.time() + (timeout if timeout is not None else 5.0)
                ser.timeout = 0.1
                while time.time() < deadline:
                    if sess.get("last_active") is None:
                        pass
                    chunk = ser.read(4096)
                    if chunk:
                        resp += chunk
                        sess["last_active"] = time.time()
                    else:
                        if resp:
                            break
                elapsed = int((time.time() - t0) * 1000)
                text = resp.decode("utf-8", errors="replace")

                sess["last_active"] = time.time()

                AutoComMCPServer._append_io_log("SEND", sess.get("port", ""),
                                                command, text,
                                                session_id=session_id, success=True)
                return {
                    "success": True,
                    "command": command,
                    "response": text,
                    "elapsed_ms": elapsed,
                    "bytes": len(resp),
                }
            except Exception as e:
                AutoComMCPServer._append_io_log("SEND", sess.get("port", ""),
                                                command, str(e),
                                                session_id=session_id, success=False)
                return {"success": False, "error": str(e)}

        @app.post("/api/sessions/{session_id}/read", tags=["持久会话"], response_model=SessionReadResponse)
        async def session_read(
            session_id: str,
            timeout: Optional[float] = Query(None, description="等待数据的时间（秒）"),
            max_bytes: Optional[int] = Query(None, description="最大读取字节数"),
        ) -> dict:
            """读取持久会话的接收缓冲区"""
            with self._session_lock:
                sess = self._sessions.get(session_id)
            if not sess:
                raise HTTPException(status_code=404, detail="Session not found")

            ser: Any = sess.get("ser")
            if ser is None:
                raise HTTPException(status_code=500, detail="Session serial handle is closed")

            try:
                if timeout is not None:
                    ser.timeout = timeout
                max_read = max_bytes if max_bytes is not None else 4096
                resp = ser.read(max_read)
                text = resp.decode("utf-8", errors="replace")
                sess["last_active"] = time.time()
                AutoComMCPServer._append_io_log("READ", sess.get("port", ""),
                                                text, session_id=session_id,
                                                success=True)
                return {
                    "success": True,
                    "data": text,
                    "bytes_count": len(resp),
                    "session_id": session_id,
                }
            except Exception as e:
                AutoComMCPServer._append_io_log("READ", sess.get("port", ""),
                                                str(e), session_id=session_id,
                                                success=False)
                return {"success": False, "error": str(e)}

        # ─── 设备参数管理 ───

        @app.get("/api/profiles", tags=["设备配置"], response_model=ProfileListResponse)
        async def list_profiles() -> dict:
            """列出所有已保存的设备配置"""
            return await AutoComMCPServer._device_profile_list()

        @app.post("/api/profiles", tags=["设备配置"], response_model=ProfileSaveResponse)
        async def save_profile(
            name: str = Query(..., description="配置名称（唯一标识）"),
            port: str = Query(..., description="COM 端口名称"),
            baud_rate: int = Query(115200, description="波特率"),
            data_bits: int = Query(8, description="数据位"),
            stop_bits: int = Query(1, description="停止位"),
            parity: str = Query("none", description="校验位: none/even/odd/mark/space"),
            flow_control: bool = Query(False, description="RTS/CTS 流控"),
            timeout: float = Query(5.0, description="读取超时（秒）"),
            label: str = Query("", description="显示标签"),
        ) -> dict:
            """保存设备串口配置"""
            return await AutoComMCPServer._device_profile_save(
                name=name, port=port, baud_rate=baud_rate,
                data_bits=data_bits, stop_bits=stop_bits,
                parity=parity, flow_control=flow_control,
                timeout=timeout, label=label,
            )

        @app.delete("/api/profiles/{name}", tags=["设备配置"], response_model=ProfileDeleteResponse)
        async def delete_profile(name: str) -> dict:
            """删除已保存的设备配置"""
            result = await AutoComMCPServer._device_profile_delete(name=name)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=str(result.get("error", "Not found")))
            return result

        # ─── 流水线存储管理 ───

        @app.get("/api/storage/pipelines", tags=["流水线存储"], response_model=PipelineListResponse)
        async def storage_list_pipelines() -> dict:
            """列出 ~/.autocom/pipelines/ 下已保存的流水线"""
            return self._storage_list()

        @app.post("/api/storage/pipelines", tags=["流水线存储"], response_model=PipelineSaveResponse)
        async def storage_save_pipeline(
            name: str = Query(..., description="流水线名称（不含扩展名）"),
            body: PipelineSaveRequest = None,
        ) -> dict:
            """保存流水线配置文件到 ~/.autocom/pipelines/"""
            if body is None or not body.content.strip():
                raise HTTPException(status_code=400, detail="Body must contain 'content' field with YAML/JSON")
            return self._storage_save(name, body.content)

        @app.get("/api/storage/pipelines/{name}", tags=["流水线存储"], response_model=PipelineContentResponse)
        async def storage_get_pipeline(name: str) -> dict:
            """查看已保存的流水线内容"""
            return self._storage_get(name)

        @app.delete("/api/storage/pipelines/{name}", tags=["流水线存储"], response_model=PipelineDeleteResponse)
        async def storage_delete_pipeline(name: str) -> dict:
            """删除已保存的流水线"""
            return self._storage_delete(name)

        # ─── 流水线执行 ───

        @app.post("/api/pipeline/validate", tags=["流水线"], response_model=PipelineValidateResponse)
        async def validate_pipeline(
            name: Optional[str] = Query(None, description="已保存的流水线名称（与 config_content 二选一）"),
            config_content: Optional[str] = Query(None, description="YAML/JSON 配置内容（与 name 二选一）"),
        ) -> dict:
            """校验流水线配置"""
            resolved = self._resolve_pipeline(name, config_content)
            if not resolved:
                raise HTTPException(status_code=400, detail="Must provide either pipeline or config_content")
            return await AutoComMCPServer._validate_pipeline(file_path=resolved)

        @app.post("/api/pipeline/run", tags=["流水线"], response_model=PipelineRunResponse)
        async def run_pipeline(
            name: Optional[str] = Query(None, description="已保存的流水线名称（与 config_content 二选一）"),
            config_content: Optional[str] = Query(None, description="YAML/JSON 配置内容（与 name 二选一）"),
            loop_count: Optional[int] = Query(None, description="循环轮数"),
            duration: Optional[int] = Query(None, description="限时执行时长（秒）"),
            stop_on_failure: Optional[bool] = Query(None, description="失败即停止"),
        ) -> dict:
            """执行流水线"""
            resolved = self._resolve_pipeline(name, config_content)
            if not resolved:
                raise HTTPException(status_code=400, detail="Must provide either pipeline or config_content")
            duration_str = str(duration) if duration is not None else None
            return await AutoComMCPServer._run_pipeline(
                file_path=resolved, loop_count=loop_count, duration=duration_str, stop_on_failure=stop_on_failure,
            )

        @app.post("/api/pipeline/dry-run", tags=["流水线"], response_model=PipelineDryRunResponse)
        async def dry_run(
            name: Optional[str] = Query(None, description="已保存的流水线名称（与 config_content 二选一）"),
            config_content: Optional[str] = Query(None, description="YAML/JSON 配置内容（与 name 二选一）"),
        ) -> dict:
            """干运行：解析变量、追踪控制流，不执行 I/O"""
            resolved = self._resolve_pipeline(name, config_content)
            if not resolved:
                raise HTTPException(status_code=400, detail="Must provide either pipeline or config_content")
            return await AutoComMCPServer._pipeline_dry_run(file_path=resolved)

        @app.post("/api/pipeline/step-debug", tags=["流水线"], response_model=PipelineStepDebugResponse)
        async def step_debug(
            name: Optional[str] = Query(None, description="已保存的流水线名称（与 config_content 二选一）"),
            config_content: Optional[str] = Query(None, description="YAML/JSON 配置内容（与 name 二选一）"),
            step_id: str = Query(..., description="要调试的步骤 ID"),
        ) -> dict:
            """单步调试：只执行流水线中的某一个步骤"""
            resolved = self._resolve_pipeline(name, config_content)
            if not resolved:
                raise HTTPException(status_code=400, detail="Must provide either pipeline or config_content")
            return await AutoComMCPServer._pipeline_step_debug(file_path=resolved, step_id=step_id)

        # ─── 执行历史 ───

        @app.get("/api/executions", tags=["执行历史"], response_model=ExecutionListResponse)
        async def list_executions(limit: int = Query(20, description="最多返回的会话数")) -> dict:
            """列出最近执行会话"""
            return await AutoComMCPServer._execution_list(limit=limit)

        @app.get("/api/executions/search", tags=["执行历史"], response_model=LogSearchResponse)
        async def search_all_logs(
            keyword: str = Query(..., description="搜索关键词（大小写不敏感）"),
            max_results: int = Query(50, description="最大返回匹配数"),
        ) -> dict:
            """在所有执行日志（跨会话 + 操作日志）中搜索关键词"""
            return await AutoComMCPServer._log_search_global(
                keyword=keyword, max_results=max_results,
            )

        @app.get("/api/executions/{session_id}", tags=["执行历史"], response_model=ExecutionReportResponse)
        async def get_execution(
            session_id: str,
            filename: Optional[str] = Query(None, description="指定日志文件名，返回原始内容"),
        ):
            """获取执行会话详情，或通过 ?filename=name 下载原始日志"""
            if filename:
                from pathlib import Path
                log_file = Path("logs/run") / session_id / file
                if not log_file.is_file():
                    # 尝试 operations 日志
                    log_file = Path("logs/operations") / file
                if not log_file.is_file() or log_file.parent.name not in (session_id, "operations"):
                    raise HTTPException(status_code=404, detail="Log file not found")
                return Response(
                    content=log_file.read_text("utf-8", errors="replace"),
                    media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'inline; filename="{file}"'},
                )
            result = await AutoComMCPServer._execution_report(session_id=session_id)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=str(result.get("error", "Not found")))
            return result

        @app.get("/api/executions/{session_id}/search", tags=["执行历史"], response_model=LogSearchResponse)
        async def search_session_logs(
            session_id: str,
            keyword: str = Query(..., description="搜索关键词（大小写不敏感）"),
            max_results: int = Query(50, description="最大返回匹配数"),
        ) -> dict:
            """在指定执行会话的设备日志中搜索关键词"""
            return await AutoComMCPServer._session_log_query(
                session_id=session_id, keyword=keyword, max_results=max_results,
            )

    # ── 会话清理 ──

    def _session_cleanup_worker(self) -> None:
        """后台线程：定期关闭超时空闲会话"""
        while True:
            time.sleep(self.session_cleanup_interval)
            now = time.time()
            to_close: list[tuple[str, dict[str, Any]]] = []
            with self._session_lock:
                for sid, sess in list(self._sessions.items()):
                    idle = now - sess.get("last_active", now)
                    if idle > self.session_idle_timeout:
                        to_close.append((sid, sess))
                        del self._sessions[sid]
            for sid, sess in to_close:
                ser = sess.get("ser")
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

    # ── 关闭所有会话 ──

    def _close_all_sessions(self) -> None:
        with self._session_lock:
            for sid, sess in list(self._sessions.items()):
                ser = sess.get("ser")
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass
            self._sessions.clear()

    # ── 配置解析 ──

    def _pipeline_dir(self) -> pathlib.Path:
        """~/.autocom/pipelines/ 目录，自动创建。"""
        d = pathlib.Path.home() / ".autocom" / "pipelines"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _resolve_pipeline(self, pipeline: Optional[str], config_content: Optional[str]) -> Optional[str]:
        """解析流水线来源：pipeline 名称 → 读取 ~/.autocom/pipelines/ 下的文件。"""
        if config_content and config_content.strip():
            import tempfile
            import yaml
            import json as _json
            data = None
            try:
                data = yaml.safe_load(config_content)
            except Exception:
                try:
                    data = _json.loads(config_content)
                except Exception:
                    raise HTTPException(status_code=400, detail="config_content is not valid YAML or JSON")
            if not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="config_content must parse to a JSON object")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
            try:
                yaml.safe_dump(data, tmp, sort_keys=False, allow_unicode=True)
            except Exception:
                _json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.close()
            return tmp.name
        if pipeline:
            p = self._pipeline_dir() / f"{pipeline}.yaml"
            if not p.is_file():
                p = self._pipeline_dir() / f"{pipeline}.yml"
            if not p.is_file():
                p = self._pipeline_dir() / f"{pipeline}.json"
            if not p.is_file():
                raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline}' not found in ~/.autocom/pipelines/")
            return str(p.resolve())
        return None

    def _storage_list(self) -> dict:
        """列出 ~/.autocom/pipelines/ 下所有流水线文件。"""
        d = self._pipeline_dir()
        items = []
        for f in sorted(d.iterdir()):
            if f.suffix in (".yaml", ".yml", ".json") and f.is_file():
                items.append({
                    "name": f.stem,
                    
                    "size_bytes": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                })
        return {"success": True, "total": len(items), "pipelines": items}

    def _storage_save(self, name: str, content: str) -> dict:
        """保存流水线到 ~/.autocom/pipelines/。"""
        d = self._pipeline_dir()
        p = d / f"{name}.yaml"
        p.write_text(content, encoding="utf-8")
        return {"success": True, "name": name}

    def _storage_get(self, name: str) -> dict:
        """读取已保存的流水线内容。"""
        d = self._pipeline_dir()
        for ext in (".yaml", ".yml", ".json"):
            p = d / f"{name}{ext}"
            if p.is_file():
                return {"success": True, "name": name, "content": p.read_text("utf-8"), "size_bytes": p.stat().st_size}
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")

    def _storage_delete(self, name: str) -> dict:
        """删除已保存的流水线。"""
        d = self._pipeline_dir()
        for ext in (".yaml", ".yml", ".json"):
            p = d / f"{name}{ext}"
            if p.is_file():
                p.unlink()
                return {"success": True, "name": name}
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")

    # ── 启动 ──

    def run(self) -> None:
        logger.log_info(
            f"Starting REST API server: http://{self.host}:{self.port}"
        )
        logger.log_info(f"Swagger UI: http://{self.host}:{self.port}/docs")
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )


def main() -> None:
    if not _FASTAPI_AVAILABLE:
        print("FastAPI is not installed. Install with: pip install fastapi uvicorn")
        raise SystemExit(1)

    import argparse
    parser = argparse.ArgumentParser(description="AutoCom REST API Server")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    args = parser.parse_args()

    server = AutoComRESTServer(host=args.host, port=args.port)
    try:
        server.run()
    except KeyboardInterrupt:
        logger.log_info("REST API Server interrupted, shutting down...")
    finally:
        server._close_all_sessions()


if __name__ == "__main__":
    main()
