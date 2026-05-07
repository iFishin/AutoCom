#!/usr/bin/env python3
"""
AutoCom MCP Server - Model Context Protocol 接口服务

通过 MCP 协议暴露 AutoCom 的串口操作能力，供 AI Agent / LLM 调用。
支持设备扫描、指令执行、字典加载、串口监听等核心功能。

使用方式:
    autocom mcp                      # 启动 MCP server (stdio 模式)
    autocom mcp --sse                # 启动 MCP server (SSE 模式)
    autocom mcp --port 8080          # 自定义端口
"""

from __future__ import annotations

import json
import sys
import time
import threading
from typing import Any, Optional, TYPE_CHECKING

# runtime presence flag for the optional `mcp` dependency
_MCP_AVAILABLE = False

if TYPE_CHECKING:
    # Static type imports for IDEs / type checkers only
    from mcp.server import Server as MCPServer  # type: ignore
    from mcp.server.stdio import stdio_server  # type: ignore
    from mcp.types import Tool, TextContent, CallToolResult  # type: ignore
    from mcp.shared.exceptions import McpError  # type: ignore
    from mcp import ErrorData  # type: ignore
else:
    # Runtime import guarded to avoid hard dependency at module import time
    try:
        from mcp.server import Server as MCPServer
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent, CallToolResult
        from mcp.shared.exceptions import McpError
        from mcp import ErrorData

        _MCP_AVAILABLE = True
    except Exception:  # pragma: no cover
        _MCP_AVAILABLE = False

# ---------------------------------------------------------------------------
# AutoCom 核心组件
# ---------------------------------------------------------------------------
from components.Logger import AutoComLogger, get_logger
from components.CommandExecutor import CommandExecutor
from components.CommandDeviceDict import CommandDeviceDict
from components.DataStore import DataStore
from utils.dirs import get_dirs

logger: AutoComLogger = get_logger("AutoCom.MCP")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------


class AutoComMCPServer:
    """AutoCom 的 MCP Server 实现"""

    def __init__(
        self,
        server_name: str = "autocom",
        sse_host: str = "0.0.0.0",
        sse_port: int = 8888,
    ):
        self.server_name = server_name
        self.sse_host = sse_host
        self.sse_port = sse_port
        self._server: Optional[MCPServer] = None
        self._session_lock = threading.Lock()
        self._active_devices: dict[str, Any] = {}  # name -> device manager

        # 初始化路径
        self._dirs = get_dirs()

    # ======================================================================
    # Server Lifecycle
    # ======================================================================

    def _init_server(self) -> "MCPServer":
        """初始化 MCP Server 实例并注册所有工具"""
        if not _MCP_AVAILABLE:
            raise RuntimeError("mcp 库未安装。请运行: pip install mcp")

        # 在运行时确保需要的 mcp 类型已导入（避免模块顶层导入失败导致名称未绑定）
        from mcp.server import Server as MCPServer
        from mcp.types import Tool, TextContent, CallToolResult
        from mcp.shared.exceptions import McpError

        server = MCPServer(self.server_name)

        # ------------------- list_devices -------------------
        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [
                Tool(
                    name="list_devices",
                    description="列出当前可用的串口设备及其信息",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                ),
                Tool(
                    name="execute_command",
                    description="向指定串口设备发送单条指令并返回响应",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_name": {
                                "type": "string",
                                "description": "设备名称（来自 list_devices 或自定义）",
                            },
                            "port": {
                                "type": "string",
                                "description": "串口路径，如 /dev/ttyUSB0, COM3",
                            },
                            "baud_rate": {
                                "type": "integer",
                                "description": "波特率，默认 115200",
                                "default": 115200,
                            },
                            "command": {
                                "type": "string",
                                "description": "要发送的指令内容",
                            },
                            "timeout": {
                                "type": "number",
                                "description": "等待响应的超时时间（秒），默认 5.0",
                                "default": 5.0,
                            },
                            "line_ending": {
                                "type": "string",
                                "description": "行结尾，默认 0d0a (CRLF)",
                                "default": "0d0a",
                            },
                            "hex_mode": {
                                "type": "boolean",
                                "description": "是否以十六进制发送指令",
                                "default": False,
                            },
                        },
                        "required": ["port", "command"],
                    },
                ),
                Tool(
                    name="execute_commands",
                    description="批量执行多条指令（支持串行/并行），返回所有结果",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_name": {
                                "type": "string",
                                "description": "设备名称",
                            },
                            "port": {
                                "type": "string",
                                "description": "串口路径",
                            },
                            "baud_rate": {
                                "type": "integer",
                                "description": "波特率，默认 115200",
                                "default": 115200,
                            },
                            "commands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "要执行的指令列表",
                            },
                            "parallel": {
                                "type": "boolean",
                                "description": "是否并行执行所有指令，默认 False（串行）",
                                "default": False,
                            },
                            "timeout": {
                                "type": "number",
                                "description": "每条指令的超时时间（秒），默认 5.0",
                                "default": 5.0,
                            },
                        },
                        "required": ["port", "commands"],
                    },
                ),
                Tool(
                    name="load_dict",
                    description="加载并解析 AutoCom 字典 JSON 配置文件，返回设备与指令配置",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "字典 JSON 文件的路径",
                            },
                            "config_path": {
                                "type": "string",
                                "description": "可选的配置文件路径",
                            },
                        },
                        "required": ["file_path"],
                    },
                ),
                Tool(
                    name="monitor_port",
                    description="监听串口设备输出（持续读取），返回一段时间内的输出内容",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "port": {
                                "type": "string",
                                "description": "串口路径",
                            },
                            "baud_rate": {
                                "type": "integer",
                                "description": "波特率，默认 115200",
                                "default": 115200,
                            },
                            "duration": {
                                "type": "number",
                                "description": "监听时长（秒），默认 10.0",
                                "default": 10.0,
                            },
                        },
                        "required": ["port"],
                    },
                ),
            ]

        # ------------------- call_tool -------------------
        @server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> CallToolResult:
            try:
                if name == "list_devices":
                    result = await self._list_devices()
                elif name == "execute_command":
                    result = await self._execute_command(**arguments)
                elif name == "execute_commands":
                    result = await self._execute_commands(**arguments)
                elif name == "load_dict":
                    result = await self._load_dict(**arguments)
                elif name == "monitor_port":
                    result = await self._monitor_port(**arguments)
                else:
                    error_msg = ErrorData(
                        code=-1,
                        message=f"未知工具: {name}",
                    )
                    raise McpError(error_msg)

                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
                )
            except McpError:
                raise
            except Exception as e:
                logger.log_error(f"MCP tool '{name}' failed: {e}")
                return CallToolResult(
                    isError=True,
                    content=[TextContent(type="text", text=f"Error: {e}")],
                )

        self._server = server
        return server

    # ======================================================================
    # Tool Implementations
    # ======================================================================

    @staticmethod
    async def _list_devices() -> dict:
        """扫描可用串口设备"""
        import serial.tools.list_ports

        ports = serial.tools.list_ports.comports()
        devices = []
        for p in ports:
            devices.append({
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "vid": p.vid,
                "pid": p.pid,
                "serial_number": p.serial_number,
                "manufacturer": p.manufacturer,
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
        """向串口发送指令并获取响应"""
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

            # 解析行结尾
            if isinstance(line_ending, str):
                try:
                    le_bytes = bytes.fromhex(line_ending.replace(" ", ""))
                except ValueError:
                    le_bytes = line_ending.encode()
            else:
                le_bytes = line_ending

            # 发送指令
            if hex_mode:
                cmd_bytes = bytes.fromhex(command.replace(" ", ""))
            else:
                cmd_bytes = command.encode() + le_bytes

            ser.write(cmd_bytes)

            # 读取响应
            if timeout > 0:
                time.sleep(0.1)  # 给设备一点时间响应
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
        commands: list[str],
        baud_rate: int = 115200,
        parallel: bool = False,
        timeout: float = 5.0,
        device_name: Optional[str] = None,
    ) -> dict:
        """批量执行多条指令"""
        results = []

        if parallel:
            # 并行执行（使用线程池简化）
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
                        results.append({
                            "success": False,
                            "command": cmd,
                            "error": str(e),
                        })
        else:
            # 串行执行
            for cmd in commands:
                result = await AutoComMCPServer._execute_command(
                    port=port,
                    command=cmd,
                    baud_rate=baud_rate,
                    timeout=timeout,
                    device_name=device_name,
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
    ) -> dict:
        """同步版本的 execute_command（用于线程池）"""
        import asyncio

        return asyncio.run(
            AutoComMCPServer._execute_command(
                port=port, command=command, baud_rate=baud_rate, timeout=timeout
            )
        )

    @staticmethod
    async def _load_dict(
        file_path: str,
        config_path: Optional[str] = None,
    ) -> dict:
        """加载并解析 AutoCom 字典 JSON 配置文件"""
        import os

        # 解析路径
        path = file_path
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)

        if not os.path.exists(path):
            return {
                "success": False,
                "error": f"文件不存在: {path}",
            }

        try:
            with open(path, "r", encoding="utf-8") as f:
                dict_data = json.load(f)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON 格式错误: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"文件读取失败: {e}",
            }

        # 如果提供了 config_path，合并配置
        config = None
        if config_path:
            config_p = config_path
            if not os.path.isabs(config_p):
                config_p = os.path.join(os.getcwd(), config_p)
            if os.path.exists(config_p):
                try:
                    with open(config_p, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception:
                    pass

        return {
            "success": True,
            "file_path": path,
            "config_merged": config is not None,
            "summary": AutoComMCPServer._summarize_dict(dict_data),
            "data": dict_data,
        }

    @staticmethod
    def _summarize_dict(dict_data: dict) -> dict:
        """摘要字典配置信息"""
        devices = dict_data.get("devices", [])
        commands = dict_data.get("commands", [])
        constants = dict_data.get("constants", {})
        config_for_device = dict_data.get("config_for_device", {})
        config_for_commands = dict_data.get("config_for_commands", {})

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
    async def _monitor_port(
        port: str,
        baud_rate: int = 115200,
        duration: float = 10.0,
    ) -> dict:
        """监听串口输出"""
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
                timeout=0.5,
            )

            while time.time() - start_time < duration:
                data = ser.read_all()
                if data:
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except Exception:
                        text = data.hex(" ")
                    outputs.append({
                        "timestamp": round((time.time() - start_time) * 1000, 1),
                        "data": text,
                    })
                time.sleep(0.05)

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
            return {
                "success": False,
                "port": port,
                "error": f"串口错误: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "port": port,
                "error": str(e),
            }

    # ======================================================================
    # Run
    # ======================================================================

    async def run_stdio(self) -> None:
        """以 stdio 模式运行 MCP Server（默认，适合 Claude Desktop 等）"""
        if not _MCP_AVAILABLE:
            print("Error: mcp 库未安装。请运行: pip install mcp")
            sys.exit(1)

        server = self._init_server()

        # 运行并允许通过 Ctrl+C 优雅停止
        import asyncio

        try:
            async with stdio_server() as (read_stream, write_stream):
                logger.log_info("MCP Server (stdio) 已启动 — 等待协议通信...")
                await server.run(
                    read_stream=read_stream,
                    write_stream=write_stream,
                    initialization_options=server.create_initialization_options(),
                )
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.log_info("MCP Server (stdio) 接收到停止信号，正在关闭...")
            # async with 上下文会自动关闭 stdio 连接，尽量让协程返回
            return

    async def run_sse(self) -> None:
        """以 SSE 模式运行 MCP Server（HTTP 服务）"""
        if not _MCP_AVAILABLE:
            print("Error: mcp 库未安装。请运行: pip install mcp")
            sys.exit(1)

        server = self._init_server()

        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        import uvicorn

        sse = SseServerTransport("/mcp/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await server.run(
                    read_stream=read_stream,
                    write_stream=write_stream,
                    initialization_options=server.create_initialization_options(),
                )

        app = Starlette(
            routes=[
                Route("/mcp/sse", endpoint=handle_sse),
                Mount("/mcp/messages/", app=sse.handle_post_message),
            ],
        )

        logger.log_info(f"MCP Server (SSE) 启动在 http://{self.sse_host}:{self.sse_port}/mcp/sse")
        logger.log_info(f"健康检查: http://{self.sse_host}:{self.sse_port}/health")
        logger.log_info("连接后可通过 MCP Inspector 调试: https://github.com/modelcontextprotocol/inspector")

        # 添加健康检查路由
        from starlette.responses import JSONResponse

        async def health(request):
            return JSONResponse({
                "status": "ok",
                "server": self.server_name,
                "tools": ["list_devices", "execute_command", "execute_commands", "load_dict", "monitor_port"],
            })

        # 显式注册路由，避免依赖装饰器语法在某些运行/检查环境出错
        app.add_route("/health", health)

        config = uvicorn.Config(app, host=self.sse_host, port=self.sse_port, log_level="info")
        server_uv = uvicorn.Server(config)
        try:
            await server_uv.serve()
        except Exception as e:
            # 捕获 KeyboardInterrupt/取消等导致的异常，优雅退出
            import asyncio

            if isinstance(e, (KeyboardInterrupt, asyncio.CancelledError)):
                logger.log_info("MCP Server (SSE) 接收到停止信号，正在关闭...")
                server_uv.should_exit = True
                return
            raise


# ============================================================================
# CLI 入口
# ============================================================================


def main():
    """MCP Server CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="AutoCom MCP Server - 为 AI Agent 提供串口操作能力",
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        help="以 SSE (HTTP) 模式运行（默认: stdio 模式）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8888,
        help="SSE 模式下的监听端口（默认: 8888）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="SSE 模式下的监听地址（默认: 0.0.0.0）",
    )

    args = parser.parse_args()

    if not _MCP_AVAILABLE:
        print("Error: mcp 库未安装。请运行: pip install mcp")
        sys.exit(1)

    import asyncio

    server = AutoComMCPServer(sse_host=args.host, sse_port=args.port)

    try:
        if args.sse:
            asyncio.run(server.run_sse())
        else:
            asyncio.run(server.run_stdio())
    except (KeyboardInterrupt, asyncio.CancelledError):
        # 避免 Ctrl+C 导致未捕获的 traceback，优雅退出
        logger.log_info("MCP Server 收到终止信号，正在退出...")
        try:
            sys.exit(0)
        except SystemExit:
            # 在某些运行环境 asyncio.run 会把 CancelledError 转为 KeyboardInterrupt，
            # 确保不再抛出异常到上层
            return


if __name__ == "__main__":
    main()