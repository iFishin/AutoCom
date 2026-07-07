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
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn

    _FASTAPI_AVAILABLE = True
except Exception:
    _FASTAPI_AVAILABLE = False


# 复用 MCPServer 的串口操作方法
from components.MCPServer import AutoComMCPServer
from components.Logger import AutoComLogger, get_logger

logger: AutoComLogger = get_logger("AutoCom.API")


class AutoComRESTServer:
    """AutoCom REST API Server — 基于 FastAPI。"""

    session_idle_timeout: float = 300.0  # 5 分钟无操作自动关闭
    session_cleanup_interval: float = 30.0

    def __init__(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        self.host = host
        self.port = port

        self.app = FastAPI(
            title="AutoCom REST API",
            version="1.0.0",
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

        @app.get("/api/health", tags=["系统"])
        async def health() -> dict:
            return {
                "status": "ok",
                "version": "1.0.0",
                "sessions": len(self._sessions),
            }

        # ─── 串口基础操作 ───

        @app.get("/api/ports", tags=["串口操作"])
        async def list_ports() -> dict:
            """列出当前可用的串口设备"""
            return await AutoComMCPServer._list_serial_ports()

        @app.post("/api/ports/{port}/command", tags=["串口操作"])
        async def execute_command(
            port: str,
            command: str = Query(..., description="要发送的指令"),
            baud_rate: int = Query(115200, description="波特率"),
            timeout: float = Query(5.0, description="响应超时（秒）"),
            line_ending: str = Query("0d0a", description="行结尾的十六进制字节"),
            hex_mode: bool = Query(False, description="以十六进制字节发送"),
        ) -> dict:
            """向串口设备发送单条指令"""
            return await AutoComMCPServer._execute_serial_command(
                port=port,
                command=command,
                baud_rate=baud_rate,
                timeout=timeout,
                line_ending=line_ending,
                hex_mode=hex_mode,
            )

        @app.post("/api/ports/{port}/baud-scan", tags=["串口操作"])
        async def baud_scan(
            port: str,
            test_command: str = Query("AT", description="发送的测试指令"),
            expected_response: str = Query("OK", description="期望收到的响应"),
        ) -> dict:
            """自动尝试常用波特率，找到能收到期望响应的那个"""
            return await AutoComMCPServer._serial_baud_scan(
                port=port,
                test_command=test_command,
                expected_response=expected_response,
            )

        @app.get("/api/ports/{port}/hex-dump", tags=["串口操作"])
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

        @app.get("/api/ports/{port}/pin-status", tags=["串口操作"])
        async def pin_status(
            port: str,
            baud_rate: int = Query(115200, description="波特率"),
        ) -> dict:
            """读取串口信号线状态（CTS/DSR/DCD/RI）"""
            return await AutoComMCPServer._serial_pin_status(
                port=port, baud_rate=baud_rate
            )

        @app.post("/api/ports/{port}/pin-set", tags=["串口操作"])
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

        @app.post("/api/ports/{port}/loopback", tags=["串口操作"])
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

        @app.post("/api/ports/{port}/latency", tags=["串口操作"])
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

        @app.post("/api/sessions", tags=["持久会话"])
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

        @app.get("/api/sessions", tags=["持久会话"])
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

        @app.get("/api/sessions/{session_id}", tags=["持久会话"])
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

        @app.delete("/api/sessions/{session_id}", tags=["持久会话"])
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

        @app.post("/api/sessions/{session_id}/send", tags=["持久会话"])
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

            line_ending_bytes = bytes.fromhex(line_ending) if line_ending else b"\r\n"
            send_bytes = command.encode("utf-8") + line_ending_bytes

            t0 = time.time()
            try:
                ser.write(send_bytes)
                wait_timeout = timeout if timeout is not None else sess.get("baud_rate", 115200) / 100
                ser.timeout = max(0.5, wait_timeout)
                resp = ser.read(4096)
                elapsed = int((time.time() - t0) * 1000)
                text = resp.decode("utf-8", errors="replace")

                sess["last_active"] = time.time()

                return {
                    "success": True,
                    "command": command,
                    "response": text,
                    "elapsed_ms": elapsed,
                    "bytes": len(resp),
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        @app.post("/api/sessions/{session_id}/read", tags=["持久会话"])
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
                return {
                    "success": True,
                    "data": text,
                    "bytes_count": len(resp),
                    "session_id": session_id,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # ─── 设备参数管理 ───

        @app.get("/api/profiles", tags=["设备配置"])
        async def list_profiles() -> dict:
            """列出所有已保存的设备配置"""
            return await AutoComMCPServer._device_profile_list()

        @app.post("/api/profiles", tags=["设备配置"])
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

        @app.delete("/api/profiles/{name}", tags=["设备配置"])
        async def delete_profile(name: str) -> dict:
            """删除已保存的设备配置"""
            result = await AutoComMCPServer._device_profile_delete(name=name)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=str(result.get("error", "Not found")))
            return result

        # ─── 流水线 ───

        @app.get("/api/pipelines")
        async def list_pipelines(base_dir: Optional[str] = Query(None, description="搜索目录")) -> dict:
            """列出可用流水线配置文件"""
            return await AutoComMCPServer._pipeline_list(base_dir=base_dir)

        @app.post("/api/pipeline/validate", tags=["流水线"])
        async def validate_pipeline(
            file_path: str = Query(..., description="配置文件路径"),
            config_path: Optional[str] = Query(None, description="独立的配置覆盖文件"),
            config_overrides: Optional[str] = Query(None, description="JSON 格式的配置覆盖"),
        ) -> dict:
            """校验流水线配置"""
            overrides = json.loads(config_overrides) if config_overrides else None
            return await AutoComMCPServer._validate_pipeline(
                file_path=file_path, config_path=config_path, config_overrides=overrides,
            )

        @app.post("/api/pipeline/run", tags=["流水线"])
        async def run_pipeline(
            file_path: str = Query(..., description="配置文件路径"),
            loop_count: Optional[int] = Query(None, description="循环轮数"),
            duration: Optional[str] = Query(None, description="限时: 30s, 5m, 1h"),
            stop_on_failure: Optional[bool] = Query(None, description="失败即停止"),
            config_overrides: Optional[str] = Query(None, description="JSON 格式的配置覆盖"),
        ) -> dict:
            """执行流水线"""
            overrides = json.loads(config_overrides) if config_overrides else None
            return await AutoComMCPServer._run_pipeline(
                file_path=file_path,
                loop_count=loop_count,
                duration=duration,
                stop_on_failure=stop_on_failure,
                config_overrides=overrides,
            )

        @app.post("/api/pipeline/dry-run", tags=["流水线"])
        async def dry_run(
            file_path: str = Query(..., description="配置文件路径"),
            config_overrides: Optional[str] = Query(None, description="JSON 格式的配置覆盖"),
        ) -> dict:
            """干运行：解析变量、追踪控制流，不执行 I/O"""
            overrides = json.loads(config_overrides) if config_overrides else None
            return await AutoComMCPServer._pipeline_dry_run(
                file_path=file_path, config_overrides=overrides,
            )

        @app.post("/api/pipeline/step-debug", tags=["流水线"])
        async def step_debug(
            file_path: str = Query(..., description="配置文件路径"),
            step_id: str = Query(..., description="要调试的步骤 ID"),
            config_overrides: Optional[str] = Query(None, description="JSON 格式的配置覆盖"),
        ) -> dict:
            """单步调试：只执行流水线中的某一个步骤"""
            overrides = json.loads(config_overrides) if config_overrides else None
            return await AutoComMCPServer._pipeline_step_debug(
                file_path=file_path, step_id=step_id, config_overrides=overrides,
            )

        # ─── 执行历史 ───

        @app.get("/api/executions", tags=["执行历史"])
        async def list_executions(limit: int = Query(20, description="最多返回的会话数")) -> dict:
            """列出最近执行会话"""
            return await AutoComMCPServer._execution_list(limit=limit)

        @app.get("/api/executions/{session_id}", tags=["执行历史"])
        async def get_execution(session_id: str) -> dict:
            """解析指定执行会话的日志和结果"""
            result = await AutoComMCPServer._execution_report(session_id=session_id)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=str(result.get("error", "Not found")))
            return result

        @app.get("/api/executions/{session_id}/search", tags=["执行历史"])
        async def search_logs(
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
