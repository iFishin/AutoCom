import json

from AutoCom import execute_with_loop


class TestAutoComCLI:
    def test_cli_execution(self, patched_serial, tmp_path, monkeypatch):
        # execute_with_loop 会用默认（None）目录写设备日志，隔离到临时 cwd 避免污染仓库
        monkeypatch.chdir(tmp_path)

        dict_data = {
            "ConfigForDevices": {"baud_rate": 9600, "status": "enabled"},
            "Devices": [
                {
                    "name": "DeviceA",
                    "port": "COM1",
                    "baud_rate": 9600,
                    "status": "enabled",
                }
            ],
            "Commands": [
                {
                    "command": "CMD1",
                    "expected_responses": ["HELLO"],
                    "device": "DeviceA",
                    "order": 1,
                    "timeout": 1000,
                },
                {
                    "command": "CMD2",
                    "expected_responses": ["THIS"],
                    "device": "DeviceA",
                    "order": 2,
                    "timeout": 1000,
                },
                {
                    "command": "CMD3",
                    "expected_responses": ["AUTOCOM"],
                    "device": "DeviceA",
                    "order": 3,
                    "timeout": 1000,
                },
                {
                    "command": "CMD4",
                    "expected_responses": ["UNKNOWN"],
                    "device": "DeviceA",
                    "order": 4,
                    "timeout": 1000,
                },
                {
                    "command": "CMD5",
                    "expected_responses": ["OK"],
                    "device": "DeviceA",
                    "order": 5,
                    "timeout": 1000,
                },
            ],
        }

        dict_path = tmp_path / "dict.json"
        dict_path.write_text(json.dumps(dict_data), encoding="utf-8")

        # 命令 -> 响应映射（含 CRLF）
        patched_serial.command_responses = {
            "CMD1": b"HELLO\r\n",
            "CMD2": b"THIS\r\n",
            "CMD3": b"AUTOCOM\r\n",
            "CMD4": b"UNKNOWN\r\n",
            "CMD5": b"ERROR\r\n",
        }

        # 运行 CLI（3 轮）
        execute_with_loop(str(dict_path), loop_count=3)

        # 执行后模拟串口缓冲应为空（响应已被消费）
        assert bytes(patched_serial._buffer) == b""
