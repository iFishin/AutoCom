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
import io
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

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

    session_idle_timeout = 300.0  # 5 分钟无操作自动关闭
    session_cleanup_interval = 30.0

    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
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
        self._sessions: dict[str, dict] = {}
        self._session_lock = threading.Lock()

        # 后台会话清理
        self._cleanup_thread = threading.Thread(
            target=self._session_cleanup_worker, daemon=True
        )
        self._cleanup_thread.start()

        # 注册路由
        self._register_routes()

    # ── 路由注册 ──

    def _register_routes(self):
        app = self.app

        # ─── 健康检查 ───

        @app.get("/api/health")
        async def health():
            return {
                "status": "ok",
                "version": "1.0.0",
                "sessions": len(self._sessions),
            }

        # ─── 串口基础操作 ───

        @app.get("/api/ports")
        async def list_ports():
            """列出当前可用的串口设备"""
            result = await AutoComMCPServer._list_serial_ports()
            return result

        @app.post("/api/ports/{port}/command")
        async def execute_command(
            port: str,
            command: str = Query(..., description="要发送的指令"),
            baud_rate: int = Query(115200),
            timeout: float = Query(5.0),
            line_ending: str = Query("0d0a"),
            hex_mode: bool = Query(False),
        ):
            """向串口设备发送单条指令"""
            result = await AutoComMCPServer._execute_serial_command(
                port=port,
                command=command,
                baud_rate=baud_rate,
                timeout=timeout,
                line_ending=line_ending,
                hex_mode=hex_mode,
            )
            return result

        @app.post("/api/ports/{port}/baud-scan")
        async def baud_scan(
            port: str,
            test_command: str = Query("AT"),
            expected_response: str = Query("OK"),
        ):
            """自动尝试常用波特率，找到能收到期望响应的那个"""
            result = await AutoComMCPServer._serial_baud_scan(
                port=port,
                test_command=test_command,
                expected_response=expected_response,
            )
            return result

        @app.get("/api/ports/{port}/hex-dump")
        async def hex_dump(
            port: str,
            baud_rate: int = Query(115200),
            bytes_to_read: int = Query(256),
            timeout: float = Query(3.0),
        ):
            """以 hex + ASCII 格式读取串口数据"""
            result = await AutoComMCPServer._serial_hex_dump(
                port=port,
                baud_rate=baud_rate,
                bytes_to_read=bytes_to_read,
                timeout=timeout,
            )
            return result

        @app.get("/api/ports/{port}/pin-status")
        async def pin_status(port: str, baud_rate: int = Query(115200)):
            """读取串口信号线状态（CTS/DSR/DCD/RI）"""
            result = await AutoComMCPServer._serial_pin_status(
                port=port, baud_rate=baud_rate
            )
            return result

        @app.post("/api/ports/{port}/pin-set")
        async def pin_set(
            port: str,
            baud_rate: int = Query(115200),
            dtr: Optional[bool] = Query(None),
            rts: Optional[bool] = Query(None),
        ):
            """设置 DTR/RTS 输出电平"""
            result = await AutoComMCPServer._serial_pin_set(
                port=port, baud_rate=baud_rate, dtr=dtr, rts=rts
            )
            return result

        @app.post("/api/ports/{port}/loopback")
        async def loopback_test(
            port: str,
            mode: str = Query("hardware"),
            baud_rate: int = Query(115200),
            test_data: Optional[str] = Query(None),
            probe_command: str = Query("AT"),
            probe_expected: str = Query("OK"),
            timeout: float = Query(3.0),
        ):
            """串口回环测试"""
            result = await AutoComMCPServer._serial_loopback_test(
                port=port,
                mode=mode,
                baud_rate=baud_rate,
                test_data=test_data,
                probe_command=probe_command,
                probe_expected=probe_expected,
                timeout=timeout,
            )
            return result

        @app.post("/api/ports/{port}/latency")
        async def latency_bench(
            port: str,
            baud_rate: int = Query(115200),
            rounds: int = Query(10),
            test_data: str = Query("AT"),
            timeout: float = Query(5.0),
        ):
            """串口收发延迟基准测试"""
            result = await AutoComMCPServer._serial_latency_bench(
                port=port,
                baud_rate=baud_rate,
                rounds=rounds,
                test_data=test_data,
                timeout=timeout,
            )
            return result

        # ─── 串口监视 (WebSocket) ───

        @app.websocket("/api/ports/{port}/monitor")
        async def monitor_port(websocket: WebSocket, port: str, baud_rate: int = 115200):
            """实时监视串口输出（WebSocket）"""
            await websocket.accept()
            import serial

            ser = None
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

                buffer = b""
                while True:
                    try:
                        data = ser.read(256)
                        if data:
                            buffer += data
                            text = data.decode("utf-8", errors="replace")
                            await websocket.send_json({
                                "type": "data",
                                "text": text,
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

        @app.post("/api/sessions")
        async def open_session(
            port: str,
            baud_rate: int = 115200,
            timeout: float = 5.0,
            label: Optional[str] = None,
        ):
            """打开一个持久串口会话"""
            import serial

            session_id = f"sess_{uuid.uuid4().hex[:12]}"
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
            except Exception as e:
                return {"success": False, "error": str(e)}

            session = {
                "session_id": session_id,
                "port": port,
                "baud_rate": baud_rate,
                "label": label or f"{port}@{baud_rate}",
                "ser": ser,
                "created_at": time.time(),
                "last_active": time.time(),
                "monitor": False,
                "monitor_buffer": None,
                "monitor_thread": None,
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

        @app.get("/api/sessions")
        async def list_sessions():
            """列出所有活跃的持久会话"""
            sessions = []
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

        @app.get("/api/sessions/{session_id}")
        async def get_session(session_id: str):
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
                    "monitor": sess.get("monitor", False),
                }

        @app.delete("/api/sessions/{session_id}")
        async def close_session(session_id: str):
            """关闭并清理持久会话"""
            with self._session_lock:
                sess = self._sessions.pop(session_id, None)
            if not sess:
                raise HTTPException(status_code=404, detail="Session not found")
            try:
                sess["ser"].close()
            except Exception:
                pass
            return {"success": True, "session_id": session_id}

        @app.post("/api/sessions/{session_id}/send")
        async def session_send(
            session_id: str,
            command: str = Query(..., description="要发送的指令"),
            timeout: Optional[float] = Query(None, description="响应等待超时"),
            line_ending: str = Query("0d0a"),
        ):
            """在持久会话中发送指令"""
            with self._session_lock:
                sess = self._sessions.get(session_id)
            if not sess:
                raise HTTPException(status_code=404, detail="Session not found")

            ser = sess["ser"]
            line_ending_bytes = bytes.fromhex(line_ending) if line_ending else b"\r\n"
            send_bytes = command.encode("utf-8") + line_ending_bytes

            t0 = time.time()
            try:
                ser.write(send_bytes)
                wait_timeout = timeout or sess.get("baud_rate", 115200) / 100
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

        @app.post("/api/sessions/{session_id}/read")
        async def session_read(
            session_id: str,
            timeout: Optional[float] = Query(None),
            max_bytes: Optional[int] = Query(None),
        ):
            """读取持久会话的接收缓冲区"""
            with self._session_lock:
                sess = self._sessions.get(session_id)
            if not sess:
                raise HTTPException(status_code=404, detail="Session not found")

            ser = sess["ser"]
            try:
                if timeout is not None:
                    ser.timeout = timeout
                max_read = max_bytes or 4096
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

        @app.get("/api/profiles")
        async def list_profiles():
            """列出所有已保存的设备配置"""
            result = await AutoComMCPServer._device_profile_list()
            return result

        @app.post("/api/profiles")
        async def save_profile(
            name: str = Query(...),
            port: str = Query(...),
            baud_rate: int = Query(115200),
            data_bits: int = Query(8),
            stop_bits: int = Query(1),
            parity: str = Query("none"),
            flow_control: bool = Query(False),
            timeout: float = Query(5.0),
            label: str = Query(""),
        ):
            """保存设备串口配置"""
            result = await AutoComMCPServer._device_profile_save(
                name=name, port=port, baud_rate=baud_rate,
                data_bits=data_bits, stop_bits=stop_bits,
                parity=parity, flow_control=flow_control,
                timeout=timeout, label=label,
            )
            return result

        @app.delete("/api/profiles/{name}")
        async def delete_profile(name: str):
            """删除已保存的设备配置"""
            result = await AutoComMCPServer._device_profile_delete(name=name)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
            return result

        # ─── 流水线 ───

        @app.get("/api/pipelines")
        async def list_pipelines(base_dir: Optional[str] = Query(None)):
            """列出可用流水线配置文件"""
            result = await AutoComMCPServer._pipeline_list(base_dir=base_dir)
            return result

        @app.post("/api/pipeline/validate")
        async def validate_pipeline(file_path: str = Query(...)):
            """校验流水线配置"""
            result = await AutoComMCPServer._validate_pipeline(file_path=file_path)
            return result

        @app.post("/api/pipeline/run")
        async def run_pipeline(
            file_path: str = Query(...),
            loop_count: Optional[int] = Query(None),
            duration: Optional[str] = Query(None),
            stop_on_failure: Optional[bool] = Query(None),
        ):
            """执行流水线"""
            result = await AutoComMCPServer._run_pipeline(
                file_path=file_path,
                loop_count=loop_count,
                duration=duration,
                stop_on_failure=stop_on_failure,
            )
            return result

        @app.post("/api/pipeline/dry-run")
        async def dry_run(file_path: str = Query(...)):
            """干运行：解析变量、追踪控制流，不执行 I/O"""
            result = await AutoComMCPServer._pipeline_dry_run(file_path=file_path)
            return result

        @app.post("/api/pipeline/step-debug")
        async def step_debug(
            file_path: str = Query(...),
            step_id: str = Query(...),
        ):
            """单步调试：只执行流水线中的某一个步骤"""
            result = await AutoComMCPServer._pipeline_step_debug(
                file_path=file_path, step_id=step_id,
            )
            return result

        # ─── 执行历史 ───

        @app.get("/api/executions")
        async def list_executions(limit: int = Query(20)):
            """列出最近执行会话"""
            result = await AutoComMCPServer._execution_list(limit=limit)
            return result

        @app.get("/api/executions/{session_id}")
        async def get_execution(session_id: str):
            """解析指定执行会话的日志和结果"""
            result = await AutoComMCPServer._execution_report(session_id=session_id)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
            return result

        @app.get("/api/executions/{session_id}/search")
        async def search_logs(
            session_id: str,
            keyword: str = Query(...),
            max_results: int = Query(50),
        ):
            """在指定执行会话的设备日志中搜索关键词"""
            result = await AutoComMCPServer._session_log_query(
                session_id=session_id, keyword=keyword, max_results=max_results,
            )
            return result

    # ── 会话清理 ──

    def _session_cleanup_worker(self):
        """后台线程：定期关闭超时空闲会话"""
        while True:
            time.sleep(self.session_cleanup_interval)
            now = time.time()
            to_close = []
            with self._session_lock:
                for sid, sess in list(self._sessions.items()):
                    idle = now - sess.get("last_active", now)
                    if idle > self.session_idle_timeout:
                        to_close.append((sid, sess))
                        del self._sessions[sid]
            for sid, sess in to_close:
                try:
                    sess["ser"].close()
                except Exception:
                    pass

    # ── 关闭所有会话 ──

    def _close_all_sessions(self):
        with self._session_lock:
            for sid, sess in list(self._sessions.items()):
                try:
                    sess["ser"].close()
                except Exception:
                    pass
            self._sessions.clear()

    # ── 启动 ──

    def run(self):
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


def main():
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
