from types import SimpleNamespace

import pytest

from components.Device import Device
from components.Logger import AutoComLogger

logger = AutoComLogger.get_instance(name="TestLogger")


class SimulatedSerial:
    """轻量的测试用模拟串口。

    - 支持 `is_open`、`open()` / `close()`
    - 提供 `in_waiting` 属性、`read(n)`、`write(data)`、`flush()`
    - `command_responses` 可被测试用例设置为 dict
    - `_buffer` 暴露给测试以便直接注入数据
    - 可通过 `set_owner(device)` 使用设备的 `line_ending_bytes`
    """

    def __init__(self):
        self.is_open = True
        self._buffer = bytearray()
        self.command_responses = {}
        self.owner = None

    def set_owner(self, device):
        self.owner = device

    @property
    def in_waiting(self):
        return len(self._buffer)

    def read(self, n=1):
        if n is None:
            n = len(self._buffer)
        to_read = bytes(self._buffer[:n])
        del self._buffer[: len(to_read)]
        return to_read

    def write(self, data):
        try:
            le = getattr(self.owner, "line_ending_bytes", b"\r\n")
            if le and isinstance(data, (bytes, bytearray)) and data.endswith(le):
                cmd_bytes = data[: -len(le)]
            else:
                cmd_bytes = data
            cmd = (
                cmd_bytes.decode("utf-8", errors="ignore")
                if isinstance(cmd_bytes, (bytes, bytearray))
                else str(cmd_bytes)
            )
        except Exception:
            cmd = ""

        resp = self.command_responses.get(cmd)
        if resp is None:
            return

        if isinstance(resp, (bytes, bytearray)):
            self._buffer[:] = resp
        elif isinstance(resp, str):
            self._buffer[:] = resp.encode("utf-8")
        elif isinstance(resp, list):
            parts = []
            for v in resp:
                if isinstance(v, str):
                    parts.append(v.encode("utf-8"))
                else:
                    parts.append(bytes(v))
            self._buffer[:] = b"".join(parts)
        else:
            raise TypeError("Unsupported response type for command_responses")

    def flush(self):
        pass

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False


class TestDevice:
    @pytest.fixture
    def serial_env(self, mocker):
        # Patch serial.Serial to return our SimulatedSerial
        mock_serial_class = mocker.patch("components.Device.serial.Serial")

        # Patch CommonUtils to avoid printing in tests
        mock_utils = mocker.patch("components.Device.CommonUtils")
        mock_utils.force_decode.side_effect = lambda b: b.decode(
            "utf-8", errors="ignore"
        )

        sim_serial = SimulatedSerial()
        sim_serial.is_open = True
        mock_serial_class.return_value = sim_serial

        device = Device(name="TestDevice", port="COM1", baud_rate=9600)

        # By default no automatic command->response mapping; tests provide when needed
        command_responses = {}
        # Link the simulated serial's command_responses to the test mapping
        sim_serial.command_responses = command_responses

        return SimpleNamespace(
            device=device,
            sim_serial=sim_serial,
            serial_buffer=sim_serial._buffer,
            command_responses=command_responses,
        )

    def test_init_success(self, serial_env):
        logger.log_debug("Testing Device initialization...")
        assert serial_env.device.name == "TestDevice"
        assert serial_env.device.port == "COM1"
        assert serial_env.device.ser.is_open
        assert not serial_env.device.open_failed

    def test_get_status(self, serial_env):
        status = serial_env.device.get_status()
        logger.log_debug(f"Device status: {status}")
        assert status["name"] == "TestDevice"
        assert status["port"] == "COM1"
        assert "serial_open" in status

    def test_send_command_success(self, serial_env):
        logger.log_debug("Testing successful command sending...")
        serial_env.serial_buffer[:] = b"OK\n"
        result = serial_env.device.send_command("AT", timeout=0.1, expected_responses=["OK"])
        assert result["success"]
        assert "OK" in str(result["response"])
        assert "OK" in result["matched"]

    def test_send_command_no_response(self, serial_env):
        serial_env.serial_buffer[:] = b""
        result = serial_env.device.send_command("AT", timeout=0.05, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command with no response: {result}")
        assert not result["success"]
        assert result["matched"] == []

    def test_send_command_expected_response(self, serial_env):
        serial_env.serial_buffer[:] = b"OK\r\r\n"
        result = serial_env.device.send_command("AT", timeout=0.1, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command with OK response: {result}")
        assert result["success"]
        assert result["response"] == "OK"
        assert "OK" in result["matched"]

    def test_send_command_unexpected_response(self, serial_env):
        serial_env.serial_buffer[:] = b"ERROR\n"
        result = serial_env.device.send_command("AT", timeout=0.1, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command with ERROR response: {result}")
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
        # snapshot initial buffer as text
        response = bytes(serial_env.serial_buffer).decode("utf-8", errors="ignore")
        logger.log_debug(response)

        result = serial_env.device.send_command("AT", timeout=3.0, expected_responses=["END"])
        logger.log_debug(f"Result of send_command with long response: {result}")
        assert "END" in result["response"]
        assert "END" in result["matched"]

        logger.log_debug(f"Remaining buffer before send_command: {response}")
        assert "OK" in response
        assert "RESPONSE1" in response
        assert "RESPONSE2" in response
        assert "RESPONSE3" in response
        assert "END" in response

    def test_at_command_injects_ok(self, serial_env):
        # When expected_responses are fully matched, leftover data goes
        # into pending_rx_buffer for the next step. Unmatched pending data
        # is preserved (not consumed) so subsequent steps still see it.
        serial_env.command_responses["AT"] = b"OK\r\nEND\r\n"
        res = serial_env.device.send_command("AT", timeout=0.5, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command for 'AT': {res}")
        assert res["success"]
        # OK is matched; END is leftover in pending_rx_buffer
        assert res["response"] == "OK"
        assert "OK" in res["matched"]

        serial_env.command_responses["ATM"] = b"OK\r\nOP1\r\nEND\r\n"
        res = serial_env.device.send_command("ATM", timeout=0.5, expected_responses=["OP1"])
        logger.log_debug(f"Result of send_command for 'ATM': {res}")
        assert res["success"]
        # END was in pending buffer but doesn't match OP1 — it's preserved,
        # not consumed. So the response only has OK and OP1 from serial.
        assert res["response"] == "OK\nOP1"
        assert "OP1" in res["matched"]

    def test_send_command_sequence(self, serial_env):
        # Configure responses for multiple commands
        serial_env.command_responses["CMD1"] = b"RESP1\r\n"
        serial_env.command_responses["CMD2"] = b"RESP2\r\n"
        serial_env.command_responses["CMD3"] = b"RESP3\r\n"

        res1 = serial_env.device.send_command(
            "CMD1", timeout=0.5, expected_responses=["RESP1"]
        )
        logger.log_debug(f"Result of send_command for 'CMD1': {res1}")
        assert res1["success"]
        assert "RESP1" in res1["response"]

        res2 = serial_env.device.send_command(
            "CMD2", timeout=0.5, expected_responses=["RESP2"]
        )
        logger.log_debug(f"Result of send_command for 'CMD2': {res2}")
        assert res2["success"]
        assert "RESP2" in res2["response"]

        res3 = serial_env.device.send_command(
            "CMD3", timeout=0.5, expected_responses=["RESP3"]
        )
        logger.log_debug(f"Result of send_command for 'CMD3': {res3}")
        assert res3["success"]
        assert "RESP3" in res3["response"]
