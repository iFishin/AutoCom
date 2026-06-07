#!/usr/bin/env python3
"""
AutoCom MCP Server - FastMCP 重构实现

使用 FastMCP 暴露 AutoCom 的串口操作能力，支持 stdio、SSE、Streamable HTTP 三种运行模式。
保留原有工具实现（扫描串口、执行指令、批量执行、加载字典、监听串口），并将它们注册为 FastMCP 工具。
"""

from __future__ import annotations

import asyncio
import json
import time
import inspect
import sys
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from typing import Any, Optional, List

try:
    from fastmcp import FastMCP
    _FASTMCP_AVAILABLE = True
except Exception:  # pragma: no cover
    FastMCP = None
    _FASTMCP_AVAILABLE = False

from components.Logger import AutoComLogger, get_logger
logger: AutoComLogger = get_logger("AutoCom.MCP")


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
            )

        @mcp.tool()
        async def execute_commands(
            port: str,
            commands: List[str],
            baud_rate: int = 115200,
            parallel: bool = False,
            timeout: float = 5.0,
            device_name: Optional[str] = None,
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
            )

        @mcp.tool()
        async def load_dict(file_path: str, config_path: Optional[str] = None) -> dict:
            """加载并解析 AutoCom 字典 JSON 配置文件，返回设备与指令配置"""
            logger.log_info(f"MCP: load_dict {file_path}")
            return await AutoComMCPServer._load_dict(file_path=file_path, config_path=config_path)

        @mcp.tool()
        async def monitor_port(port: str, baud_rate: int = 115200, duration: float = 10.0) -> dict:
            """监听串口设备输出（持续读取），返回一段时间内的输出内容"""
            logger.log_info(f"MCP: monitor_port {port} duration={duration}")
            return await AutoComMCPServer._monitor_port(port=port, baud_rate=baud_rate, duration=duration)

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
    ) -> dict:
        import serial

        start_time = time.time()
        response_data = ""
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
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

            if timeout > 0:
                await asyncio.sleep(0.1)
                while True:
                    data = ser.read_all()
                    if data:
                        try:
                            response_data += data.decode("utf-8", errors="replace")
                        except Exception:
                            response_data += data.hex(" ")
                    else:
                        break

            ser.close()
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "success": True,
                "port": port,
                "command": command,
                "response": response_data.strip(),
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

    @staticmethod
    async def _execute_commands(
        port: str,
        commands: List[str],
        baud_rate: int = 115200,
        parallel: bool = False,
        timeout: float = 5.0,
        device_name: Optional[str] = None,
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
                    port=port, command=cmd, baud_rate=baud_rate, timeout=timeout, device_name=device_name
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
    def _execute_command_sync(port: str, command: str, baud_rate: int = 115200, timeout: float = 5.0) -> dict:
        import asyncio

        return asyncio.run(
            AutoComMCPServer._execute_command(port=port, command=command, baud_rate=baud_rate, timeout=timeout)
        )

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
        import serial

        outputs = []
        start_time = time.time()
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
            ser.close()
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
                return asyncio.run(res)
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
                    return asyncio.run(res)
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
            _safe_log_info("MCP Server 收到中断信号，正在退出...")
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