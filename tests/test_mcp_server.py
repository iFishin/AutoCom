"""MCP Server 单元测试

测试 AutoCom MCP Server 的核心功能：
- list_devices（模拟串口扫描）
- execute_command（模拟串口通信）
- execute_commands（批量执行）
- load_dict（字典文件加载）
- monitor_port（串口监听）
"""

import unittest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock


class TestMCPServer(unittest.TestCase):
    """测试 MCP Server 核心功能"""

    def setUp(self):
        # 延迟导入，防止缺少依赖时整组测试失败
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

        import asyncio
        result = asyncio.run(self.server_class._list_devices())

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["devices"], [])

    @patch("serial.tools.list_ports.comports")
    def test_list_devices_with_devices(self, mock_comports):
        """扫描串口 — 返回模拟设备信息"""
        from unittest.mock import MagicMock

        mock_port = MagicMock()
        mock_port.device = "/dev/ttyUSB0"
        mock_port.description = "USB Serial Port"
        mock_port.hwid = "USB VID:PID=1234:5678"
        mock_port.vid = 0x1234
        mock_port.pid = 0x5678
        mock_port.serial_number = "ABC123"
        mock_port.manufacturer = "FTDI"
        mock_comports.return_value = [mock_port]

        import asyncio
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

        import asyncio
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

        import asyncio
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
        import asyncio

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
        """自定义行结尾"""
        mock_ser = MagicMock()
        mock_ser.read_all.return_value = b""
        mock_serial_class.return_value = mock_ser

        import asyncio
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

        import asyncio
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

    @patch("components.MCPServer.AutoComMCPServer._execute_command_sync")
    def test_execute_commands_parallel(self, mock_sync_exec):
        """批量并行执行指令"""
        mock_sync_exec.side_effect = [
            {"success": True, "command": "AT1", "response": "OK1"},
            {"success": True, "command": "AT2", "response": "OK2"},
        ]

        import asyncio
        result = asyncio.run(self.server_class._execute_commands(
            port="/dev/ttyUSB0",
            commands=["AT1", "AT2"],
            parallel=True,
        ))

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["parallel"], True)

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
            import asyncio
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
        import asyncio
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
            f.write("这不是 JSON {{{{\"")
            tmp_path = f.name

        try:
            import asyncio
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
            import asyncio
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

        import asyncio
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

        import asyncio
        result = asyncio.run(self.server_class._monitor_port(
            port="COM1", duration=0.1
        ))

        self.assertFalse(result["success"])
        self.assertIn("Access denied", result["error"])


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