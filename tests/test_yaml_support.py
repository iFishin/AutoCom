import unittest
import os
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from AutoCom import load_commands_from_file
from components.Logger import AutoComLogger

# 获取 logger 实例
logger = AutoComLogger.get_instance(name="TestLogger")


class TestYAMLSupport(unittest.TestCase):
    """测试 YAML 配置文件支持"""

    def setUp(self):
        """测试前准备"""
        # 获取测试文件路径
        self.test_dir = Path(__file__).parent
        self.yaml_file = self.test_dir / "dict.yaml"
        self.json_file = self.test_dir / "dict.json"

    def test_load_yaml_file(self):
        """测试加载 YAML 文件"""
        logger.log_debug("Testing YAML file loading...")

        yaml_data = load_commands_from_file(str(self.yaml_file))

        # 验证加载的数据结构
        self.assertIsInstance(yaml_data, dict)
        self.assertIn("Devices", yaml_data)
        self.assertIn("Commands", yaml_data)

        # 验证设备和命令数量
        devices = yaml_data.get("Devices", [])
        commands = yaml_data.get("Commands", [])

        self.assertEqual(len(devices), 1)
        self.assertEqual(len(commands), 3)

        logger.log_debug(
            f"✅ YAML file loaded successfully: {len(devices)} devices, {len(commands)} commands"
        )

    def test_load_json_file(self):
        """测试加载 JSON 文件"""
        logger.log_debug("Testing JSON file loading...")

        json_data = load_commands_from_file(str(self.json_file))

        # 验证加载的数据结构
        self.assertIsInstance(json_data, dict)
        self.assertIn("Devices", json_data)
        self.assertIn("Commands", json_data)

        # 验证设备和命令数量
        devices = json_data.get("Devices", [])
        commands = json_data.get("Commands", [])

        self.assertEqual(len(devices), 1)
        self.assertEqual(len(commands), 3)

        logger.log_debug(
            f"✅ JSON file loaded successfully: {len(devices)} devices, {len(commands)} commands"
        )

    def test_yaml_and_json_consistency(self):
        """测试 YAML 和 JSON 加载的数据一致性"""
        logger.log_debug("Testing YAML and JSON data consistency...")

        yaml_data = load_commands_from_file(str(self.yaml_file))
        json_data = load_commands_from_file(str(self.json_file))

        # 比较设备数量
        yaml_devices = yaml_data.get("Devices", [])
        json_devices = json_data.get("Devices", [])
        self.assertEqual(len(yaml_devices), len(json_devices))
        logger.log_debug(f"✅ Device count matches: {len(yaml_devices)}")

        # 比较命令数量
        yaml_commands = yaml_data.get("Commands", [])
        json_commands = json_data.get("Commands", [])
        self.assertEqual(len(yaml_commands), len(json_commands))
        logger.log_debug(f"✅ Command count matches: {len(yaml_commands)}")

        # 比较第一个设备
        if yaml_devices and json_devices:
            self.assertEqual(yaml_devices[0]["name"], json_devices[0]["name"])
            self.assertEqual(yaml_devices[0]["port"], json_devices[0]["port"])
            logger.log_debug(f"✅ First device matches: {yaml_devices[0]['name']}")

        # 比较第一条命令
        if yaml_commands and json_commands:
            self.assertEqual(yaml_commands[0]["command"], json_commands[0]["command"])
            self.assertEqual(yaml_commands[0]["order"], json_commands[0]["order"])
            logger.log_debug(f"✅ First command matches: {yaml_commands[0]['command']}")

    def test_unsupported_file_format(self):
        """测试不支持的文件格式"""
        logger.log_debug("Testing unsupported file format handling...")

        # 创建临时文件测试错误处理
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test")
            temp_file = f.name

        try:
            # 应该抛出 ValueError
            with self.assertRaises(ValueError) as context:
                load_commands_from_file(temp_file)

            # 验证错误信息
            error_msg = str(context.exception)
            self.assertIn("Unsupported file format", error_msg)
            self.assertIn(".txt", error_msg)
            logger.log_debug(f"✅ Correctly rejected unsupported format: {error_msg}")

        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_yaml_with_yml_extension(self):
        """测试 .yml 扩展名的 YAML 文件"""
        logger.log_debug("Testing .yml extension support...")

        # 创建 .yml 文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("""Devices:
  - name: TestDevice
    port: COM1
    baud_rate: 9600
Commands:
  - command: AT
    device: TestDevice
    order: 1
    timeout: 1000
""")
            temp_file = f.name

        try:
            # 应该能够加载
            data = load_commands_from_file(temp_file)

            self.assertIsInstance(data, dict)
            self.assertIn("Devices", data)
            self.assertIn("Commands", data)

            logger.log_debug("✅ .yml extension supported correctly")

        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_yaml_encoding_handling(self):
        """测试 YAML 文件的编码处理"""
        logger.log_debug("Testing YAML file encoding handling...")

        # 创建 UTF-8 编码的 YAML 文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("""Devices:
  - name: 测试设备
    port: COM1
    baud_rate: 9600
Commands:
  - command: AT
    device: 测试设备
    order: 1
    timeout: 1000
""")
            temp_file = f.name

        try:
            # 应该能够正确加载 UTF-8 编码
            data = load_commands_from_file(temp_file)

            self.assertIsInstance(data, dict)
            devices = data.get("Devices", [])
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["name"], "测试设备")

            logger.log_debug("✅ UTF-8 encoding handled correctly")

        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_yaml_expected_responses_string(self):
        """测试 YAML 中 expected_responses 的字符串格式"""
        logger.log_debug("Testing YAML expected_responses as strings...")

        yaml_data = load_commands_from_file(str(self.yaml_file))
        commands = yaml_data.get("Commands", [])

        # 验证所有 expected_responses 都是字符串
        for cmd in commands:
            if "expected_responses" in cmd:
                for resp in cmd["expected_responses"]:
                    self.assertIsInstance(
                        resp,
                        str,
                        f"Expected response should be string, got {type(resp)}: {resp}",
                    )

        # 特别验证包含冒号的响应
        csub_command = next(
            (cmd for cmd in commands if "CSUB" in cmd.get("command", "")), None
        )
        if csub_command and "expected_responses" in csub_command:
            expected_resp = csub_command["expected_responses"][0]
            self.assertIsInstance(expected_resp, str)
            self.assertIn("SubEdition: V01", expected_resp)
            logger.log_debug(
                f"✅ Expected response with colon handled correctly: {expected_resp}"
            )


if __name__ == "__main__":
    unittest.main(buffer=False, verbosity=2)
