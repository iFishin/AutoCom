from types import SimpleNamespace

import pytest

from components.Device import Device


class TestDevice:
    @pytest.fixture
    def serial_env(self, mocker, patched_serial):
        # CommonUtils.force_decode 用于把响应字节解码为文本
        mock_utils = mocker.patch("components.Device.CommonUtils")
        mock_utils.force_decode.side_effect = lambda b: b.decode(
            "utf-8", errors="ignore"
        )

        command_responses = {}
        patched_serial.command_responses = command_responses

        device = Device(name="TestDevice", port="COM1", baud_rate=9600)

        return SimpleNamespace(
            device=device,
            serial_buffer=patched_serial._buffer,
            command_responses=command_responses,
        )

    def test_init_success(self, serial_env):
        assert serial_env.device.name == "TestDevice"
        assert serial_env.device.port == "COM1"
        assert serial_env.device.ser.is_open
        assert not serial_env.device.open_failed

    def test_get_status(self, serial_env):
        status = serial_env.device.get_status()
        assert status["name"] == "TestDevice"
        assert status["port"] == "COM1"
        assert "serial_open" in status

    def test_send_command_success(self, serial_env):
        serial_env.serial_buffer[:] = b"OK\n"
        result = serial_env.device.send_command(
            "AT", timeout=0.1, expected_responses=["OK"]
        )
        assert result["success"]
        assert "OK" in str(result["response"])
        assert "OK" in result["matched"]

    def test_send_command_no_response(self, serial_env):
        serial_env.serial_buffer[:] = b""
        result = serial_env.device.send_command(
            "AT", timeout=0.05, expected_responses=["OK"]
        )
        assert not result["success"]
        assert result["matched"] == []

    def test_send_command_expected_response(self, serial_env):
        serial_env.serial_buffer[:] = b"OK\r\r\n"
        result = serial_env.device.send_command(
            "AT", timeout=0.1, expected_responses=["OK"]
        )
        assert result["success"]
        assert result["response"] == "OK"
        assert "OK" in result["matched"]

    def test_send_command_unexpected_response(self, serial_env):
        serial_env.serial_buffer[:] = b"ERROR\n"
        result = serial_env.device.send_command(
            "AT", timeout=0.1, expected_responses=["OK"]
        )
        assert not result["success"]
        assert result["response"] == "ERROR"
        assert "OK" not in result["matched"]

    def test_send_command_long_response(self, serial_env):
        parts = [
            b"OK\r\n",
            b"RESPONSE1\r\n",
            b"RESPONSE2\r\n",
            b"RESPONSE3\r\n",
            b"END\r\n",
        ]
        serial_env.serial_buffer[:] = b"".join(parts)
        response = bytes(serial_env.serial_buffer).decode("utf-8", errors="ignore")

        result = serial_env.device.send_command(
            "AT", timeout=3.0, expected_responses=["END"]
        )
        assert "END" in result["response"]
        assert "END" in result["matched"]

        assert "OK" in response
        assert "RESPONSE1" in response
        assert "RESPONSE2" in response
        assert "RESPONSE3" in response
        assert "END" in response

    def test_at_command_injects_ok(self, serial_env):
        # expected_responses 全部匹配后，剩余数据进入 pending_rx_buffer；
        # 未匹配的 pending 数据会被保留（不消费），供后续步骤使用。
        serial_env.command_responses["AT"] = b"OK\r\nEND\r\n"
        res = serial_env.device.send_command(
            "AT", timeout=0.5, expected_responses=["OK"]
        )
        assert res["success"]
        # OK 已匹配；END 留在 pending_rx_buffer
        assert res["response"] == "OK"
        assert "OK" in res["matched"]

        serial_env.command_responses["ATM"] = b"OK\r\nOP1\r\nEND\r\n"
        res = serial_env.device.send_command(
            "ATM", timeout=0.5, expected_responses=["OP1"]
        )
        assert res["success"]
        # END 在 pending buffer 里但不匹配 OP1，被保留而非消费，
        # 因此 response 只包含串口来的 OK 和 OP1。
        assert res["response"] == "OK\nOP1"
        assert "OP1" in res["matched"]

    def test_send_command_sequence(self, serial_env):
        serial_env.command_responses["CMD1"] = b"RESP1\r\n"
        serial_env.command_responses["CMD2"] = b"RESP2\r\n"
        serial_env.command_responses["CMD3"] = b"RESP3\r\n"

        res1 = serial_env.device.send_command(
            "CMD1", timeout=0.5, expected_responses=["RESP1"]
        )
        assert res1["success"]
        assert "RESP1" in res1["response"]

        res2 = serial_env.device.send_command(
            "CMD2", timeout=0.5, expected_responses=["RESP2"]
        )
        assert res2["success"]
        assert "RESP2" in res2["response"]

        res3 = serial_env.device.send_command(
            "CMD3", timeout=0.5, expected_responses=["RESP3"]
        )
        assert res3["success"]
        assert "RESP3" in res3["response"]
