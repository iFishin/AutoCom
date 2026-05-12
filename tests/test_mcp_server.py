"""MCP Server 单元测试

测试 AutoCom MCP Server 的核心功能：
- list_devices（模拟串口扫描）
- execute_command（模拟串口通信）
- execute_commands（批量执行）
- load_dict（字典文件加载）
- monitor_port（串口监听）
- LineEnding 枚举
- Prompt 模板
- Resource 读取
- 客户端配置打印
- MCP 不可用时的退出行为
"""

import unittest
import json
import tempfile
import os
import sys
import io
import asyncio
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock


# ============================================================================
# LineEnding 枚举测试
# ============================================================================


class TestLineEnding(unittest.TestCase):
    """测试 LineEnding 枚举"""

    def setUp(self):
        from components.MCPServer import LineEnding
        self.LE = LineEnding

    def test_crlf_default(self):
        """CRLF 默认值"""
        self.assertEqual(self.LE.CRLF.value, "0d0a")

    def test_lf_value(self):
        """LF 值"""
        self.assertEqual(self.LE.LF.value, "0a")

    def test_cr_value(self):
        """CR 值"""
        self.assertEqual(self.LE.CR.value, "0d")

    def test_none_empty(self):
        """NONE 为空"""
        self.assertEqual(self.LE.NONE.value, "")

    def test_to_bytes_crlf(self):
        """CRLF 转为 \\r\\n"""
        self.assertEqual(self.LE.CRLF.to_bytes(), b"\r\n")

    def test_to_bytes_lf(self):
        """LF 转为 \\n"""
        self.assertEqual(self.LE.LF.to_bytes(), b"\n")

    def test_to_bytes_cr(self):
        """CR 转为 \\r"""
        self.assertEqual(self.LE.CR.to_bytes(), b"\r")

    def test_to_bytes_none(self):
        """NONE 转为空字节"""
        self.assertEqual(self.LE.NONE.to_bytes(), b"")

    def test_from_value_hex_string(self):
        """从旧版 hex string 解析"""
        self.assertIs(self.LE.from_value("0d0a"), self.LE.CRLF)
        self.assertIs(self.LE.from_value("0a"), self.LE.LF)
        self.assertIs(self.LE.from_value("0d"), self.LE.CR)
        self.assertIs(self.LE.from_value(""), self.LE.NONE)

    def test_from_value_name(self):
        """从枚举名称解析"""
        self.assertIs(self.LE.from_value("CRLF"), self.LE.CRLF)
        self.assertIs(self.LE.from_value("LF"), self.LE.LF)
        self.assertIs(self.LE.from_value("CR"), self.LE.CR)
        self.assertIs(self.LE.from_value("NONE"), self.LE.NONE)

    def test_from_value_spaces(self):
        """带空格的 hex string"""
        self.assertIs(self.LE.from_value("0d 0a"), self.LE.CRLF)

    def test_from_value_fallback(self):
        """未识别的值回退到 CRLF"""
        self.assertIs(self.LE.from_value("99"), self.LE.CRLF)


# ============================================================================
# MCPServer 核心测试
# ============================================================================


class TestMCPServer(unittest.TestCase):
    """测试 MCP Server 核心功能"""

    def setUp(self):
        try:
            from components.MCPServer import AutoComMCPServer
            self.server_class = AutoComMCPServer
        except ImportError:
            self.skipTest("MCP 依赖未安装 (pip install mcp)")

        self.server = self.server_class()

    # ======================================================================
    # list_devices
    # ======================================================================

    @patch("serial.tools.list_ports.comports")
    def test_list_devices_empty(self, mock_comports):
        """扫描串口 — 无设备时返回空列表"""
        mock_comports.return_value = []

        result = asyncio.run(self.server_class._list_devices())

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["devices"], [])

    @patch("serial.tools.list_ports.comports")
    def test_list_devices_with_devices(self, mock_comports):
        """扫描串口 — 返回模拟设备信息"""
        mock_port = MagicMock()
        mock_port.device = "/dev/ttyUSB0"
        mock_port.description = "USB Serial Port"
        mock_port.hwid = "USB VID:PID=1234:5678"
        mock_port.vid = 0x1234
        mock_port.pid = 0x5678
        mock_port.serial_number = "ABC123"
        mock_port.manufacturer = "FTDI"
        mock_comports.return_value = [mock_port]

        result = asyncio.run(self.server_class._list_devices())

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["devices"][0]["device"], "/dev/ttyUSB0")
        self.assertEqual(result["devices"][0]["vid"], 0x1234)
        self.assertEqual(result["devices"][0]["pid"], 0x5678)

    # ======================================================================
    # execute_command
    # ======================================================================

    @patch("serial.Serial")
    def test_execute_command_success(self, mock_serial_class):
        """发送指令并成功获取响应"""
        mock_ser = MagicMock()
        mock_ser.read_all.side_effect = [b"OK\r\n", b""]
        mock_serial_class.return_value = mock_ser

        result = asyncio.run(self.server_class._execute_command(
            port="/dev/ttyUSB0",
            command="AT",
            baud_rate=115200,
            timeout=1.0,
        ))

        self.assertTrue(result["success"])
        self.assertEqual(result["port"], "/dev/ttyUSB0")
        self.assertEqual(result["command"], "AT")
        self.assertEqual(result["response"], "OK")
        self.assertIn("elapsed_ms", result)
        mock_ser.write.assert_called_once()
        mock_ser.close.assert_called_once()

    @patch("serial.Serial")
    def test_execute_command_serial_error(self, mock_serial_class):
        """串口错误时返回失败结果"""
        import serial
        mock_serial_class.side_effect = serial.SerialException("Port not found")

        result = asyncio.run(self.server_class._execute_command(
            port="/dev/ttyFAKE",
            command="AT",
            timeout=1.0,
        ))

        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertIn("Port not found", result["error"])

    @patch("serial.Serial")
    def test_execute_command_hex_mode(self, mock_serial_class):
        """十六进制模式发送"""
        mock_ser = MagicMock()
        mock_ser.read_all.side_effect = [b"\x01\x02\x03", b""]
        mock_serial_class.return_value = mock_ser

        result = asyncio.run(self.server_class._execute_command(
            port="COM3",
            command="01 02 03",
            hex_mode=True,
            timeout=0.1,
        ))

        self.assertTrue(result["success"])
        written = mock_ser.write.call_args[0][0]
        self.assertEqual(written, bytes.fromhex("010203"))

    @patch("serial.Serial")
    def test_execute_command_custom_line_ending(self, mock_serial_class):
        """自定义行结尾 — 使用枚举名"""
        mock_ser = MagicMock()
        mock_ser.read_all.return_value = b""
        mock_serial_class.return_value = mock_ser

        result = asyncio.run(self.server_class._execute_command(
            port="/dev/ttyUSB0",
            command="AT",
            line_ending="LF",
            timeout=0.5,
        ))

        self.assertTrue(result["success"])
        written = mock_ser.write.call_args[0][0]
        self.assertTrue(written.endswith(b"\n"))

    @patch("serial.Serial")
    def test_execute_command_line_ending_hex(self, mock_serial_class):
        """自定义行结尾 — 使用旧版 hex string"""
        mock_ser = MagicMock()
        mock_ser.read_all.return_value = b""
        mock_serial_class.return_value = mock_ser

        result = asyncio.run(self.server_class._execute_command(
            port="/dev/ttyUSB0",
            command="AT",
            line_ending="0a",
            timeout=0.5,
        ))

        self.assertTrue(result["success"])
        written = mock_ser.write.call_args[0][0]
        self.assertTrue(written.endswith(b"\n"))

    # ======================================================================
    # execute_commands (batch)
    # ======================================================================

    @patch("components.MCPServer.AutoComMCPServer._execute_command")
    def test_execute_commands_serial(self, mock_exec):
        """批量串行执行指令"""
        mock_exec.side_effect = [
            {"success": True, "command": "AT", "response": "OK"},
            {"success": True, "command": "AT+GMR", "response": "v1.0"},
        ]

        result = asyncio.run(self.server_class._execute_commands(
            port="/dev/ttyUSB0",
            commands=["AT", "AT+GMR"],
            parallel=False,
        ))

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["fail_count"], 0)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(mock_exec.call_count, 2)

    @patch("components.MCPServer.AutoComMCPServer._execute_command")
    def test_execute_commands_parallel(self, mock_exec):
        """批量并行执行指令 — 使用 asyncio"""
        async def side_effect(**kwargs):
            cmd = kwargs["command"]
            return {"success": True, "command": cmd, "response": f"OK {cmd}"}

        mock_exec.side_effect = side_effect

        result = asyncio.run(self.server_class._execute_commands(
            port="/dev/ttyUSB0",
            commands=["AT1", "AT2"],
            parallel=True,
        ))

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["parallel"], True)

    @patch("components.MCPServer.AutoComMCPServer._execute_command")
    def test_execute_commands_with_line_ending(self, mock_exec):
        """批量执行时传递 line_ending 和 hex_mode 参数"""
        async def side_effect(**kwargs):
            return {"success": True, "command": kwargs["command"]}

        mock_exec.side_effect = side_effect

        result = asyncio.run(self.server_class._execute_commands(
            port="/dev/ttyUSB0",
            commands=["AT"],
            line_ending="LF",
            hex_mode=False,
        ))

        self.assertTrue(result["results"][0]["success"])
        # 验证参数被正确传递
        call_kwargs = mock_exec.call_args[1]
        self.assertEqual(call_kwargs["line_ending"], "LF")
        self.assertFalse(call_kwargs["hex_mode"])

    # ======================================================================
    # load_dict
    # ======================================================================

    def test_load_dict_success(self):
        """加载合法的字典 JSON 文件"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({
                "devices": [{"name": "DeviceA", "port": "COM1"}],
                "commands": [{"command": "AT", "device": "DeviceA"}],
                "constants": {"SSID": "MyWiFi"},
                "config_for_device": {"baud_rate": 115200},
                "config_for_commands": {},
            }, f)
            tmp_path = f.name

        try:
            result = asyncio.run(self.server_class._load_dict(file_path=tmp_path))

            self.assertTrue(result["success"])
            self.assertEqual(result["file_path"], tmp_path)
            self.assertFalse(result["config_merged"])

            summary = result["summary"]
            self.assertEqual(summary["device_count"], 1)
            self.assertEqual(summary["command_count"], 1)
            self.assertEqual(summary["device_names"], ["DeviceA"])
            self.assertTrue(summary["has_constants"])
            self.assertEqual(summary["constant_keys"], ["SSID"])
        finally:
            os.unlink(tmp_path)

    def test_load_dict_file_not_found(self):
        """加载不存在的文件返回错误"""
        result = asyncio.run(self.server_class._load_dict(
            file_path="/tmp/nonexistent_autocom_test.json"
        ))
        self.assertFalse(result["success"])
        self.assertIn("不存在", result["error"])

    def test_load_dict_invalid_json(self):
        """加载非法 JSON 文件返回错误"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("这不是 JSON {{{{\"\"")
            tmp_path = f.name

        try:
            result = asyncio.run(self.server_class._load_dict(file_path=tmp_path))
            self.assertFalse(result["success"])
            self.assertIn("JSON", result["error"])
        finally:
            os.unlink(tmp_path)

    def test_load_dict_with_config(self):
        """加载字典时合并配置文件"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"devices": [{"name": "D1", "port": "COM1"}]}, f)
            dict_path = f.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"config_for_device": {"baud_rate": 9600}}, f)
            config_path = f.name

        try:
            result = asyncio.run(self.server_class._load_dict(
                file_path=dict_path, config_path=config_path
            ))
            self.assertTrue(result["success"])
            self.assertTrue(result["config_merged"])
        finally:
            os.unlink(dict_path)
            os.unlink(config_path)

    # ======================================================================
    # monitor_port
    # ======================================================================

    @patch("serial.Serial")
    def test_monitor_port_no_output(self, mock_serial_class):
        """监听串口 — 无输出时正常返回"""
        mock_ser = MagicMock()
        mock_ser.read_all.return_value = b""
        mock_serial_class.return_value = mock_ser

        result = asyncio.run(self.server_class._monitor_port(
            port="/dev/ttyUSB0",
            duration=0.1,
        ))

        self.assertTrue(result["success"])
        self.assertEqual(result["port"], "/dev/ttyUSB0")
        self.assertEqual(result["output"], "")
        self.assertEqual(result["total_chunks"], 0)
        mock_ser.close.assert_called_once()

    @patch("serial.Serial")
    def test_monitor_port_serial_error(self, mock_serial_class):
        """监听时串口异常"""
        import serial
        mock_serial_class.side_effect = serial.SerialException("Access denied")

        result = asyncio.run(self.server_class._monitor_port(
            port="COM1", duration=0.1
        ))

        self.assertFalse(result["success"])
        self.assertIn("Access denied", result["error"])

    # ======================================================================
    # Prompts
    # ======================================================================

    def test_prompt_serial_debug(self):
        """串口调试 Prompt 模板"""
        prompt = self.server_class._get_prompt_serial_debug(
            port="/dev/ttyUSB0", baud_rate="115200"
        )
        self.assertIn("/dev/ttyUSB0", prompt.description)
        self.assertEqual(len(prompt.messages), 1)
        self.assertIn("AT", prompt.messages[0].content.text)

    def test_prompt_device_inspection(self):
        """设备巡检 Prompt 模板"""
        prompt = self.server_class._get_prompt_device_inspection(
            port="COM3", commands="AT+GMR,AT+CSQ"
        )
        self.assertIn("COM3", prompt.description)
        self.assertIn("AT+GMR", prompt.messages[0].content.text)
        self.assertIn("AT+CSQ", prompt.messages[0].content.text)

    def test_prompt_device_inspection_default_commands(self):
        """设备巡检 Prompt — 默认命令列表"""
        prompt = self.server_class._get_prompt_device_inspection(port="COM1")
        self.assertIn("AT+GMR", prompt.messages[0].content.text)
        self.assertIn("AT+CGSN", prompt.messages[0].content.text)
        self.assertIn("AT+CSQ", prompt.messages[0].content.text)

    def test_prompt_dict_run(self):
        """字典执行 Prompt 模板"""
        prompt = self.server_class._get_prompt_dict_run(
            file_path="/tmp/dict.json"
        )
        self.assertIn("/tmp/dict.json", prompt.description)
        self.assertIn("load_dict", prompt.messages[0].content.text)

    # ======================================================================
    # Resources
    # ======================================================================

    def test_resource_info(self):
        """读取 autocom://info 资源"""
        result = asyncio.run(self.server._read_resource("autocom://info"))
        self.assertEqual(len(result.contents), 1)
        data = json.loads(result.contents[0].text)
        self.assertEqual(data["server"], "autocom")
        self.assertIn("version", data)
        self.assertIn("uptime_seconds", data)

    def test_resource_tools(self):
        """读取 autocom://tools 资源"""
        result = asyncio.run(self.server._read_resource("autocom://tools"))
        self.assertEqual(len(result.contents), 1)
        data = json.loads(result.contents[0].text)
        self.assertIn("tool_count", data)
        self.assertGreater(data["tool_count"], 0)
        tool_names = [t["name"] for t in data["tools"]]
        self.assertIn("list_devices", tool_names)
        self.assertIn("execute_command", tool_names)

    @patch("serial.tools.list_ports.comports")
    def test_resource_device_found(self, mock_comports):
        """读取 autocom://devices/{port} — 设备存在"""
        mock_port = MagicMock()
        mock_port.device = "/dev/ttyUSB0"
        mock_port.description = "USB Serial"
        mock_port.hwid = "USB VID:PID=0403:6001"
        mock_port.vid = 0x0403
        mock_port.pid = 0x6001
        mock_port.serial_number = "A1"
        mock_port.manufacturer = "FTDI"
        mock_comports.return_value = [mock_port]

        result = asyncio.run(self.server._read_resource(
            "autocom://devices//dev/ttyUSB0"
        ))
        data = json.loads(result.contents[0].text)
        self.assertEqual(data["device"], "/dev/ttyUSB0")
        self.assertEqual(data["serial_number"], "A1")

    @patch("serial.tools.list_ports.comports")
    def test_resource_device_not_found(self, mock_comports):
        """读取 autocom://devices/{port} — 设备不存在"""
        mock_comports.return_value = []

        result = asyncio.run(self.server._read_resource(
            "autocom://devices//dev/ttyFAKE"
        ))
        data = json.loads(result.contents[0].text)
        self.assertIn("error", data)
        self.assertIn("未找到", data["error"])

    # ======================================================================
    # MCP 不可用时的退出行为
    # ======================================================================

    def test_main_exits_when_mcp_unavailable(self):
        """MCP 未安装时 main() 应退出码 1 并打印提示"""
        from components.MCPServer import main as mcp_main, _MCP_AVAILABLE
        orig_available = _MCP_AVAILABLE

        try:
            from components.MCPServer import main as mcp_main_mod
            mcp_main_mod._MCP_AVAILABLE = False
            orig_argv = sys.argv[:]
            sys.argv = ["autocom-mcp"]
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    mcp_main_mod.main()
            self.assertEqual(cm.exception.code, 1)
            out = buf.getvalue()
            self.assertIn("mcp 库未安装", out)
            sys.argv = orig_argv
        finally:
            from components.MCPServer import main as mcp_main_mod
            mcp_main_mod._MCP_AVAILABLE = orig_available

    def test_run_stdio_exits_when_mcp_unavailable(self):
        """MCP 未安装时 run_stdio() 应退出码 1"""
        from components.MCPServer import AutoComMCPServer, _MCP_AVAILABLE
        orig_available = _MCP_AVAILABLE

        try:
            from components.MCPServer import _MCP_AVAILABLE as _avail
            import components.MCPServer as mcp_mod
            mcp_mod._MCP_AVAILABLE = False
            server = mcp_mod.AutoComMCPServer()
            with self.assertRaises(SystemExit) as cm:
                asyncio.run(server.run_stdio())
            self.assertEqual(cm.exception.code, 1)
        finally:
            mcp_mod._MCP_AVAILABLE = orig_available


# ============================================================================
# CLI 入口测试
# ============================================================================


class TestMCPCLI(unittest.TestCase):
    """测试 MCP CLI 子命令"""

    def test_cli_import(self):
        """确保 MCPServer.main 可导入"""
        try:
            from components.MCPServer import main
            self.assertIsNotNone(main)
        except Exception as e:
            self.fail(f"导入 MCPServer.main 失败: {e}")


if __name__ == "__main__":
    unittest.main(buffer=False, verbosity=2)
