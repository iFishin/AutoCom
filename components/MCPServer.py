#!/usr/bin/env python3
"""
AutoCom MCP Server - Model Context Protocol 接口服务

通过 MCP 协议暴露 AutoCom 的串口操作能力，供 AI Agent / LLM 调用。
支持设备扫描、指令执行、字典加载、串口监听等核心功能。

使用方式:
    autocom mcp                      # 启动 MCP server (stdio 模式)
    autocom mcp --sse                # 启动 MCP server (SSE 模式)
    autocom mcp --sse --port 8080    # 自定义端口
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

# ---------------------------------------------------------------------------
# MCP SDK
# ---------------------------------------------------------------------------
try:
    from mcp.server import Server as MCPServer
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        Tool,
        TextContent,
        CallToolResult,
        Prompt,
        PromptArgument,
        GetPromptResult,
        PromptMessage,
        Resource,
        ResourceTemplate,
        ReadResourceResult,
        TextResourceContents,
    )
    from mcp.shared.exceptions import McpError

    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MCP_AVAILABLE = False

# ---------------------------------------------------------------------------
# AutoCom 核心组件
# ---------------------------------------------------------------------------
from components.Logger import AutoComLogger, get_logger
from components.CommandExecutor import CommandExecutor
from components.CommandDeviceDict import CommandDeviceDict
from components.DataStore import DataStore
from utils.dirs import get_dirs
from version import __version__

logger: AutoComLogger = get_logger("AutoCom.MCP")


# ---------------------------------------------------------------------------
# 行结尾枚举
# ---------------------------------------------------------------------------


class LineEnding(str, Enum):
    """行结尾模式"""

    CRLF = "0d0a"  # \\r\\n (Windows 风格)
    LF = "0a"  # \\n (Unix 风格)
    CR = "0d"  # \\r (旧 Mac 风格)
    NONE = ""  # 无结尾

    @classmethod
    def from_value(cls, value: str) -> "LineEnding":
        """从字符串解析行结尾，兼容旧版 hex string 传参"""
        normalized = value.replace(" ", "").lower()
        for member in cls:
            if member.value == normalized:
                return member
        # 如果不是已知的 hex 值，尝试直接匹配枚举名
        try:
            return cls[value.upper()]
        except KeyError:
            # 回退默认
            return cls.CRLF

    def to_bytes(self) -> bytes:
        """转换为实际字节"""
        if not self.value:
            return b""
        return bytes.fromhex(self.value)


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
        self._start_time: float = time.time()
        self._session_lock = threading.Lock()
        self._active_devices: dict[str, Any] = {}  # name -> device manager

        # 初始化路径
        self._dirs = get_dirs()

    # ======================================================================
    # Server Lifecycle
    # ======================================================================

    def _init_server(self) -> MCPServer:
        """初始化 MCP Server 实例并注册所有工具"""
        server = MCPServer(self.server_name)

        # ------------------- list_tools -------------------
        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return self._get_tools()

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
                    raise McpError(f"未知工具: {name}")

                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=json.dumps(
                                result, ensure_ascii=False, indent=2
                            ),
                        )
                    ]
                )
            except McpError:
                raise
            except Exception as e:
                logger.log_error(f"MCP tool '{name}' failed: {e}")
                return CallToolResult(
                    isError=True,
                    content=[TextContent(type="text", text=f"Error: {e}")],
                )

        # ------------------- list_prompts -------------------
        @server.list_prompts()
        async def handle_list_prompts() -> list[Prompt]:
            return [
                Prompt(
                    name="serial_debug",
                    description="串口调试模板：连接串口设备并执行调试命令",
                    arguments=[
                        PromptArgument(
                            name="port",
                            description="串口路径，如 /dev/ttyUSB0 或 COM3",
                            required=True,
                        ),
                        PromptArgument(
                            name="baud_rate",
                            description="波特率，默认 115200",
                            required=False,
                        ),
                    ],
                ),
                Prompt(
                    name="device_inspection",
                    description="设备巡检模板：对设备执行一系列基础检查命令",
                    arguments=[
                        PromptArgument(
                            name="port",
                            description="串口路径",
                            required=True,
                        ),
                        PromptArgument(
                            name="commands",
                            description="巡检指令列表（逗号分隔），默认 AT+GMR,AT+CGSN,AT+CSQ",
                            required=False,
                        ),
                    ],
                ),
                Prompt(
                    name="dict_run",
                    description="字典执行模板：加载 AutoCom 字典文件并执行配置的指令",
                    arguments=[
                        PromptArgument(
                            name="file_path",
                            description="字典 JSON 文件路径",
                            required=True,
                        ),
                    ],
                ),
            ]

        # ------------------- get_prompt -------------------
        @server.get_prompt()
        async def handle_get_prompt(
            name: str, arguments: dict[str, Any] | None = None
        ) -> GetPromptResult:
            args = arguments or {}
            if name == "serial_debug":
                return self._get_prompt_serial_debug(**args)
            elif name == "device_inspection":
                return self._get_prompt_device_inspection(**args)
            elif name == "dict_run":
                return self._get_prompt_dict_run(**args)
            else:
                raise McpError(f"未知 Prompt: {name}")

        # ------------------- list_resources -------------------
        @server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            return [
                Resource(
                    uri="autocom://info",
                    name="AutoCom Server Info",
                    description="AutoCom MCP Server 基本信息",
                    mimeType="application/json",
                ),
                Resource(
                    uri="autocom://tools",
                    name="Available Tools",
                    description="所有可用工具的完整描述",
                    mimeType="application/json",
                ),
            ]

        # ------------------- list_resource_templates -------------------
        @server.list_resource_templates()
        async def handle_list_resource_templates() -> list[ResourceTemplate]:
            return [
                ResourceTemplate(
                    uriTemplate="autocom://devices/{port}",
                    name="Device Info",
                    description="指定串口设备的详细信息",
                    mimeType="application/json",
                ),
            ]

        # ------------------- read_resource -------------------
        @server.read_resource()
        async def handle_read_resource(uri: str) -> ReadResourceResult:
            return await self._read_resource(uri)

        self._server = server
        return server

    # ======================================================================
    # Tool Definitions
    # ======================================================================

    @staticmethod
    def _get_tools() -> list[Tool]:
        """返回所有工具定义"""
        return [
            Tool(
                name="list_devices",
                description="列出当前可用的串口设备及其信息（端口、描述、VID/PID、序列号、制造商）",
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
                        "port": {
                            "type": "string",
                            "description": "串口路径，如 /dev/ttyUSB0, COM3",
                        },
                        "command": {
                            "type": "string",
                            "description": "要发送的指令内容",
                        },
                        "baud_rate": {
                            "type": "integer",
                            "description": "波特率，默认 115200",
                            "default": 115200,
                        },
                        "timeout": {
                            "type": "number",
                            "description": "等待响应的超时时间（秒），默认 5.0",
                            "default": 5.0,
                        },
                        "line_ending": {
                            "type": "string",
                            "description": "行结尾模式。可选值: CRLF(0d0a, 默认), LF(0a), CR(0d), NONE(无)",
                            "default": "CRLF",
                        },
                        "hex_mode": {
                            "type": "boolean",
                            "description": "是否以十六进制发送指令（command 参数应为 hex string，如 '01 02 03'）",
                            "default": False,
                        },
                        "device_name": {
                            "type": "string",
                            "description": "设备名称（可选，用于日志标记）",
                        },
                    },
                    "required": ["port", "command"],
                },
            ),
            Tool(
                name="execute_commands",
                description="批量执行多条指令（支持串行/并行），返回所有结果及统计信息",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "port": {
                            "type": "string",
                            "description": "串口路径",
                        },
                        "commands": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要执行的指令列表",
                        },
                        "baud_rate": {
                            "type": "integer",
                            "description": "波特率，默认 115200",
                            "default": 115200,
                        },
                        "parallel": {
                            "type": "boolean",
                            "description": "是否并行执行所有指令（默认 False = 串行）",
                            "default": False,
                        },
                        "timeout": {
                            "type": "number",
                            "description": "每条指令的超时时间（秒），默认 5.0",
                            "default": 5.0,
                        },
                        "line_ending": {
                            "type": "string",
                            "description": "行结尾模式。可选值: CRLF(0d0a, 默认), LF(0a), CR(0d), NONE(无)",
                            "default": "CRLF",
                        },
                        "hex_mode": {
                            "type": "boolean",
                            "description": "是否以十六进制发送指令",
                            "default": False,
                        },
                    },
                    "required": ["port", "commands"],
                },
            ),
            Tool(
                name="load_dict",
                description="加载并解析 AutoCom 字典 JSON 配置文件，返回设备与指令配置摘要",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "字典 JSON 文件的路径（支持绝对路径和相对路径）",
                        },
                        "config_path": {
                            "type": "string",
                            "description": "可选的配置文件路径，会与字典配置合并",
                        },
                    },
                    "required": ["file_path"],
                },
            ),
            Tool(
                name="monitor_port",
                description="监听串口设备输出（持续读取），返回一段时间内的所有输出内容",
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
            devices.append(
                {
                    "device": p.device,
                    "description": p.description,
                    "hwid": p.hwid,
                    "vid": p.vid,
                    "pid": p.pid,
                    "serial_number": p.serial_number,
                    "manufacturer": p.manufacturer,
                }
            )

        return {"total": len(devices), "devices": devices}

    @staticmethod
    async def _execute_command(
        port: str,
        command: str,
        baud_rate: int = 115200,
        timeout: float = 5.0,
        line_ending: str = "CRLF",
        hex_mode: bool = False,
        device_name: Optional[str] = None,
    ) -> dict:
        """向串口发送指令并获取响应"""
        import serial

        start_time = time.time()
        response_data = ""
        le = LineEnding.from_value(line_ending)

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
            if hex_mode:
                cmd_bytes = bytes.fromhex(command.replace(" ", ""))
            else:
                cmd_bytes = command.encode() + le.to_bytes()

            ser.write(cmd_bytes)

            # 读取响应
            if timeout > 0:
                await asyncio.sleep(0.1)  # 给设备一点时间响应
                while True:
                    data = ser.read_all()
                    if data:
                        try:
                            response_data += data.decode(
                                "utf-8", errors="replace"
                            )
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
                "elapsed_ms": round(
                    (time.time() - start_time) * 1000, 2
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "port": port,
                "command": command,
                "error": str(e),
                "elapsed_ms": round(
                    (time.time() - start_time) * 1000, 2
                ),
            }

    @staticmethod
    async def _execute_commands(
        port: str,
        commands: list[str],
        baud_rate: int = 115200,
        parallel: bool = False,
        timeout: float = 5.0,
        line_ending: str = "CRLF",
        hex_mode: bool = False,
        device_name: Optional[str] = None,
    ) -> dict:
        """批量执行多条指令"""
        results = []

        if parallel:
            # 使用 asyncio.gather 替代 threading 实现真正的异步并行
            async def run_one(cmd: str) -> dict:
                return await AutoComMCPServer._execute_command(
                    port=port,
                    command=cmd,
                    baud_rate=baud_rate,
                    timeout=timeout,
                    line_ending=line_ending,
                    hex_mode=hex_mode,
                    device_name=device_name,
                )

            tasks = [run_one(cmd) for cmd in commands]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # 将异常转换为错误结果
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    results[i] = {
                        "success": False,
                        "command": commands[i],
                        "error": str(r),
                    }
        else:
            # 串行执行
            for cmd in commands:
                result = await AutoComMCPServer._execute_command(
                    port=port,
                    command=cmd,
                    baud_rate=baud_rate,
                    timeout=timeout,
                    line_ending=line_ending,
                    hex_mode=hex_mode,
                    device_name=device_name,
                )
                results.append(result)

        return {
            "port": port,
            "total": len(commands),
            "parallel": parallel,
            "success_count": sum(
                1 for r in results if r.get("success")
            ),
            "fail_count": sum(
                1 for r in results if not r.get("success")
            ),
            "results": results,
        }

    @staticmethod
    async def _load_dict(
        file_path: str,
        config_path: Optional[str] = None,
    ) -> dict:
        """加载并解析 AutoCom 字典 JSON 配置文件"""
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
            "device_names": [
                d.get("name", d.get("port", "unknown"))
                for d in devices
            ],
            "command_count": len(commands),
            "command_names": [
                c.get("name", c.get("command", f"cmd_{i}"))[:50]
                for i, c in enumerate(commands)
            ],
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
                    outputs.append(
                        {
                            "timestamp": round(
                                (time.time() - start_time) * 1000, 1
                            ),
                            "data": text,
                        }
                    )
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
    # Prompt Implementations
    # ======================================================================

    @staticmethod
    def _get_prompt_serial_debug(
        port: str, baud_rate: str = "115200"
    ) -> GetPromptResult:
        """串口调试 Prompt"""
        return GetPromptResult(
            description=f"串口调试 - {port} @ {baud_rate} baud",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"请帮我调试串口设备 {port}（波特率 {baud_rate}）。\n\n"
                            "请按以下步骤操作：\n"
                            f"1. 使用 list_devices 确认 {port} 可用\n"
                            f"2. 发送 'AT' 指令测试连接（execute_command, port={port}, command=AT）\n"
                            "3. 根据 AT 回复进行后续调试\n\n"
                            "如果遇到串口错误，请耐心重试并报告错误信息。"
                        ),
                    ),
                ),
            ],
        )

    @staticmethod
    def _get_prompt_device_inspection(
        port: str, commands: str = "AT+GMR,AT+CGSN,AT+CSQ"
    ) -> GetPromptResult:
        """设备巡检 Prompt"""
        cmd_list = [c.strip() for c in commands.split(",")]
        return GetPromptResult(
            description=f"设备巡检 - {port}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"请对串口设备 {port} 执行巡检。\n\n"
                            f"需要执行的命令：{', '.join(cmd_list)}\n\n"
                            "请使用 execute_commands 批量执行上述指令，"
                            "然后汇总返回每个指令的执行结果。"
                            "如果某条指令失败，请标记出来。"
                        ),
                    ),
                ),
            ],
        )

    @staticmethod
    def _get_prompt_dict_run(file_path: str) -> GetPromptResult:
        """字典执行 Prompt"""
        return GetPromptResult(
            description=f"字典执行 - {file_path}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"请加载并执行 AutoCom 字典文件 {file_path}。\n\n"
                            "步骤：\n"
                            f"1. 使用 load_dict 加载 {file_path}，获取设备与指令配置\n"
                            "2. 根据字典配置使用 execute_command 或 execute_commands 依次执行指令\n"
                            "3. 汇总执行结果，报告成功/失败情况\n\n"
                            "注意：请严格按字典中定义的顺序和参数执行。"
                        ),
                    ),
                ),
            ],
        )

    # ======================================================================
    # Resource Implementations
    # ======================================================================

    async def _read_resource(self, uri: str) -> ReadResourceResult:
        """读取资源"""
        if uri == "autocom://info":
            return ReadResourceResult(
                contents=[
                    TextResourceContents(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps(
                            {
                                "server": self.server_name,
                                "version": __version__,
                                "started_at": datetime.fromtimestamp(
                                    self._start_time, tz=timezone.utc
                                ).isoformat(),
                                "uptime_seconds": round(
                                    time.time() - self._start_time, 1
                                ),
                                "mode": "SSE/HTTP",
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    )
                ]
            )

        if uri == "autocom://tools":
            tools = self._get_tools()
            return ReadResourceResult(
                contents=[
                    TextResourceContents(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps(
                            {
                                "tool_count": len(tools),
                                "tools": [
                                    {
                                        "name": t.name,
                                        "description": t.description,
                                        "inputSchema": t.inputSchema,
                                    }
                                    for t in tools
                                ],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    )
                ]
            )

        # 处理设备模板 URI: autocom://devices/{port}
        if uri.startswith("autocom://devices/"):
            port = uri[len("autocom://devices/"):]
            import serial.tools.list_ports

            for p in serial.tools.list_ports.comports():
                if p.device == port:
                    return ReadResourceResult(
                        contents=[
                            TextResourceContents(
                                uri=uri,
                                mimeType="application/json",
                                text=json.dumps(
                                    {
                                        "device": p.device,
                                        "description": p.description,
                                        "hwid": p.hwid,
                                        "vid": p.vid,
                                        "pid": p.pid,
                                        "serial_number": p.serial_number,
                                        "manufacturer": p.manufacturer,
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                            )
                        ]
                    )
            return ReadResourceResult(
                contents=[
                    TextResourceContents(
                        uri=uri,
                        mimeType="application/json",
                        text=json.dumps(
                            {
                                "error": f"设备 {port} 未找到",
                                "hint": "请使用 list_devices 查看可用设备列表",
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    )
                ]
            )

        raise McpError(f"未知资源: {uri}")

    # ======================================================================
    # Run
    # ======================================================================

    def _print_client_config(self, mode: str) -> None:
        """打印客户端配置提示"""
        print()
        print(f"  🚀 AutoCom MCP Server v{__version__}")
        print(f"  ⚡ Mode: {mode}")
        print()

        if mode == "SSE":
            sse_url = f"http://{self.sse_host}:{self.sse_port}/mcp/sse"
            print(f"  📡 SSE URL: {sse_url}")
            print(f"  🩺 Health:  http://{self.sse_host}:{self.sse_port}/health")
            print()
            print("  ┌─ MCP 客户端配置 ───────────────────────────────────┐")
            print("  │                                                    │")
            print(f"  │  Claude Desktop 或任何 MCP 客户端:                  │")
            print("  │                                                    │")
            print('  │  {                                            │')
            print(f'  │    "mcpServers": {{                           │')
            print(f'  │      "autocom": {{                           │')
            print(f'  │        "url": "{sse_url}"        │')
            print(f'  │      }}                                        │')
            print(f'  │    }}                                            │')
            print("  │  }                                            │")
            print("  │                                                    │")
            print("  └────────────────────────────────────────────────────┘")
        else:
            print("  📡 Mode: stdio (标准输入输出)")
            print()
            print("  ┌─ MCP 客户端配置（Claude Desktop） ────────────────┐")
            print("  │                                                    │")
            print("  │  {                                            │")
            print('  │    "mcpServers": {                           │')
            print('  │      "autocom": {                           │')
            print(f'  │        "command": "autocom",                  │')
            print(f'  │        "args": ["mcp"]                       │')
            print(f'  │      }}                                        │')
            print(f'  │    }}                                            │')
            print("  │  }                                            │")
            print("  │                                                    │")
            print("  └────────────────────────────────────────────────────┘")
        print()

    async def run_stdio(self) -> None:
        """以 stdio 模式运行 MCP Server（默认，适合 Claude Desktop 等）"""
        if not _MCP_AVAILABLE:
            print("Error: mcp 库未安装。请运行: pip install autocom[mcp]")
            sys.exit(1)

        self._print_client_config("stdio")

        server = self._init_server()

        async with stdio_server() as (read_stream, write_stream):
            logger.log_info("MCP Server (stdio) 已启动 — 等待协议通信...")
            await server.run(
                read_stream=read_stream,
                write_stream=write_stream,
                initialization_options=(
                    server.create_initialization_options()
                ),
            )

    async def run_sse(self) -> None:
        """以 SSE 模式运行 MCP Server（HTTP 服务）"""
        if not _MCP_AVAILABLE:
            print("Error: mcp 库未安装。请运行: pip install autocom[mcp]")
            sys.exit(1)

        self._print_client_config("SSE")

        server = self._init_server()

        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        from starlette.responses import JSONResponse
        import uvicorn

        sse = SseServerTransport("/mcp/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await server.run(
                    read_stream=read_stream,
                    write_stream=write_stream,
                    initialization_options=(
                        server.create_initialization_options()
                    ),
                )

        @app.route("/health")
        async def health(request):
            return JSONResponse(
                {
                    "status": "ok",
                    "server": self.server_name,
                    "version": __version__,
                    "uptime_seconds": round(
                        time.time() - self._start_time, 1
                    ),
                    "tools": [
                        "list_devices",
                        "execute_command",
                        "execute_commands",
                        "load_dict",
                        "monitor_port",
                    ],
                }
            )

        app = Starlette(
            routes=[
                Route("/mcp/sse", endpoint=handle_sse),
                Mount(
                    "/mcp/messages/",
                    app=sse.handle_post_message,
                ),
            ],
        )

        logger.log_info(
            f"MCP Server (SSE) 启动在 "
            f"http://{self.sse_host}:{self.sse_port}/mcp/sse"
        )
        logger.log_info(
            f"健康检查: "
            f"http://{self.sse_host}:{self.sse_port}/health"
        )
        logger.log_info(
            "Inspector: https://github.com/modelcontextprotocol/inspector"
        )

        config = uvicorn.Config(
            app,
            host=self.sse_host,
            port=self.sse_port,
            log_level="info",
        )
        server_uv = uvicorn.Server(config)
        await server_uv.serve()


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
        print(
            "Error: mcp 库未安装。请运行: pip install autocom[mcp]"
        )
        sys.exit(1)

    server = AutoComMCPServer(
        sse_host=args.host, sse_port=args.port
    )

    if args.sse:
        asyncio.run(server.run_sse())
    else:
        asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()