from pathlib import Path
from types import SimpleNamespace

import pytest

from AutoCom import load_commands_from_file

_TEST_DIR = Path(__file__).parent
# dict.json 被 .gitignore 忽略，仅在本地生成时存在；缺失时依赖它的用例跳过
_HAS_DICT_JSON = (_TEST_DIR / "dict.json").exists()
_SKIP_NO_JSON = pytest.mark.skipif(
    not _HAS_DICT_JSON, reason="tests/dict.json 未生成（被 .gitignore 忽略）"
)


@pytest.fixture
def yaml_files():
    return SimpleNamespace(
        yaml_file=_TEST_DIR / "dict.yaml",
        json_file=_TEST_DIR / "dict.json",
    )


class TestYAMLSupport:
    """测试 YAML 配置文件支持"""

    def test_load_yaml_file(self, yaml_files):
        yaml_data = load_commands_from_file(str(yaml_files.yaml_file))

        assert isinstance(yaml_data, dict)
        assert "Devices" in yaml_data
        assert "Commands" in yaml_data
        assert len(yaml_data.get("Devices", [])) == 1
        assert len(yaml_data.get("Commands", [])) == 3

    @_SKIP_NO_JSON
    def test_load_json_file(self, yaml_files):
        json_data = load_commands_from_file(str(yaml_files.json_file))

        assert isinstance(json_data, dict)
        assert "Devices" in json_data
        assert "Commands" in json_data
        assert len(json_data.get("Devices", [])) == 1
        assert len(json_data.get("Commands", [])) == 3

    @_SKIP_NO_JSON
    def test_yaml_and_json_consistency(self, yaml_files):
        yaml_data = load_commands_from_file(str(yaml_files.yaml_file))
        json_data = load_commands_from_file(str(yaml_files.json_file))

        yaml_devices = yaml_data.get("Devices", [])
        json_devices = json_data.get("Devices", [])
        assert len(yaml_devices) == len(json_devices)

        yaml_commands = yaml_data.get("Commands", [])
        json_commands = json_data.get("Commands", [])
        assert len(yaml_commands) == len(json_commands)

        if yaml_devices and json_devices:
            assert yaml_devices[0]["name"] == json_devices[0]["name"]
            assert yaml_devices[0]["port"] == json_devices[0]["port"]

        if yaml_commands and json_commands:
            assert yaml_commands[0]["command"] == json_commands[0]["command"]
            assert yaml_commands[0]["order"] == json_commands[0]["order"]

    def test_unsupported_file_format(self, tmp_path):
        temp_file = tmp_path / "sample.txt"
        temp_file.write_text("test", encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            load_commands_from_file(str(temp_file))

        error_msg = str(exc_info.value)
        assert "Unsupported file format" in error_msg
        assert ".txt" in error_msg

    def test_yaml_with_yml_extension(self, tmp_path):
        temp_file = tmp_path / "config.yml"
        temp_file.write_text(
            """Devices:
  - name: TestDevice
    port: COM1
    baud_rate: 9600
Commands:
  - command: AT
    device: TestDevice
    order: 1
    timeout: 1000
""",
            encoding="utf-8",
        )

        data = load_commands_from_file(str(temp_file))

        assert isinstance(data, dict)
        assert "Devices" in data
        assert "Commands" in data

    def test_yaml_encoding_handling(self, tmp_path):
        temp_file = tmp_path / "config.yaml"
        temp_file.write_text(
            """Devices:
  - name: 测试设备
    port: COM1
    baud_rate: 9600
Commands:
  - command: AT
    device: 测试设备
    order: 1
    timeout: 1000
""",
            encoding="utf-8",
        )

        data = load_commands_from_file(str(temp_file))

        assert isinstance(data, dict)
        devices = data.get("Devices", [])
        assert len(devices) == 1
        assert devices[0]["name"] == "测试设备"

    def test_yaml_expected_responses_string(self, yaml_files):
        yaml_data = load_commands_from_file(str(yaml_files.yaml_file))
        commands = yaml_data.get("Commands", [])

        for cmd in commands:
            for resp in cmd.get("expected_responses", []):
                assert isinstance(resp, str), (
                    f"Expected response should be string, got {type(resp)}: {resp}"
                )

        # 特别验证包含冒号的响应
        csub_command = next(
            (cmd for cmd in commands if "CSUB" in cmd.get("command", "")), None
        )
        assert csub_command is not None
        expected_resp = csub_command["expected_responses"][0]
        assert isinstance(expected_resp, str)
        assert "SubEdition: V01" in expected_resp
