import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from components.Device import Device
from tests import logger


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


class TestDevice(unittest.TestCase):
    def setUp(self):
        # Patch serial.Serial to return our SimulatedSerial
        patcher = patch("components.Device.serial.Serial")
        self.addCleanup(patcher.stop)
        self.mock_serial_class = patcher.start()

        # Create simulated serial and expose its buffer for tests compatibility
        self.sim_serial = SimulatedSerial()
        self.sim_serial.is_open = True
        self.mock_serial_class.return_value = self.sim_serial
        self._serial_buffer = self.sim_serial._buffer

        # Patch CommonUtils.print_log_line to avoid printing in tests
        patcher_utils = patch("components.Device.CommonUtils")
        self.addCleanup(patcher_utils.stop)
        self.mock_utils = patcher_utils.start()
        self.mock_utils.force_decode.side_effect = lambda b: b.decode(
            "utf-8", errors="ignore"
        )

        self.device = Device(name="TestDevice", port="COM1", baud_rate=9600)

        # By default no automatic command->response mapping; tests provide when needed
        self.command_responses = {}
        # Link the simulated serial's command_responses to the test mapping
        self.sim_serial.command_responses = self.command_responses

    def test_init_success(self):
        logger.log_debug("Testing Device initialization...")
        self.assertEqual(self.device.name, "TestDevice")
        self.assertEqual(self.device.port, "COM1")
        self.assertTrue(self.device.ser.is_open)
        self.assertFalse(self.device.open_failed)

    def test_get_status(self):
        status = self.device.get_status()
        logger.log_debug(f"Device status: {status}")
        self.assertEqual(status["name"], "TestDevice")
        self.assertEqual(status["port"], "COM1")
        self.assertIn("serial_open", status)

    def test_send_command_success(self):
        logger.log_debug("Testing successful command sending...")
        self._serial_buffer[:] = b"OK\n"
        result = self.device.send_command("AT", timeout=0.1, expected_responses=["OK"])
        self.assertTrue(result["success"])
        self.assertIn("OK", str(result["response"]))
        self.assertIn("OK", result["matched"])

    def test_send_command_no_response(self):
        self._serial_buffer[:] = b""
        result = self.device.send_command("AT", timeout=0.05, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command with no response: {result}")
        self.assertFalse(result["success"])
        self.assertEqual(result["matched"], [])

    def test_send_command_expected_response(self):
        self._serial_buffer[:] = b"OK\r\r\n"
        result = self.device.send_command("AT", timeout=0.1, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command with OK response: {result}")
        self.assertTrue(result["success"])
        self.assertEqual("OK", result["response"])
        self.assertIn("OK", result["matched"])

    def test_send_command_unexpected_response(self):
        self._serial_buffer[:] = b"ERROR\n"
        result = self.device.send_command("AT", timeout=0.1, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command with ERROR response: {result}")
        self.assertFalse(result["success"])
        self.assertEqual("ERROR", result["response"])
        self.assertNotIn("OK", result["matched"])

    def test_send_command_long_response(self):
        parts = [
            b"OK\r\n",
            b"RESPONSE1\r\n",
            b"RESPONSE2\r\n",
            b"RESPONSE3\r\n",
            b"END\r\n",
        ]
        self._serial_buffer[:] = b"".join(parts)
        # snapshot initial buffer as text
        response = bytes(self._serial_buffer).decode("utf-8", errors="ignore")
        logger.log_debug(response)

        result = self.device.send_command("AT", timeout=3.0, expected_responses=["END"])
        logger.log_debug(f"Result of send_command with long response: {result}")
        self.assertIn("END", result["response"])
        self.assertIn("END", result["matched"])

        logger.log_debug(f"Remaining buffer before send_command: {response}")
        self.assertIn("OK", response)
        self.assertIn("RESPONSE1", response)
        self.assertIn("RESPONSE2", response)
        self.assertIn("RESPONSE3", response)
        self.assertIn("END", response)

    def test_at_command_injects_ok(self):
        # configure mapping per-test
        self.command_responses["AT"] = b"OK\r\nEND\r\n"
        res = self.device.send_command("AT", timeout=0.5, expected_responses=["OK"])
        logger.log_debug(f"Result of send_command for 'AT': {res}")
        self.assertTrue(res["success"])
        self.assertEqual("OK\nEND", res["response"])
        self.assertIn("OK", res["matched"])

        self.command_responses["ATM"] = b"OK\r\nOP1\r\nEND\r\n"
        res = self.device.send_command("ATM", timeout=0.5, expected_responses=["OP1"])
        logger.log_debug(f"Result of send_command for 'ATM': {res}")
        self.assertTrue(res["success"])
        self.assertEqual("OK\nOP1\nEND", res["response"])
        self.assertIn("OP1", res["matched"])

    def test_send_command_sequence(self):
        # Configure responses for multiple commands
        self.command_responses["CMD1"] = b"RESP1\r\n"
        self.command_responses["CMD2"] = b"RESP2\r\n"
        self.command_responses["CMD3"] = b"RESP3\r\n"

        res1 = self.device.send_command(
            "CMD1", timeout=0.5, expected_responses=["RESP1"]
        )
        logger.log_debug(f"Result of send_command for 'CMD1': {res1}")
        self.assertTrue(res1["success"])
        self.assertIn("RESP1", res1["response"])

        res2 = self.device.send_command(
            "CMD2", timeout=0.5, expected_responses=["RESP2"]
        )
        logger.log_debug(f"Result of send_command for 'CMD2': {res2}")
        self.assertTrue(res2["success"])
        self.assertIn("RESP2", res2["response"])

        res3 = self.device.send_command(
            "CMD3", timeout=0.5, expected_responses=["RESP3"]
        )
        logger.log_debug(f"Result of send_command for 'CMD3': {res3}")
        self.assertTrue(res3["success"])
        self.assertIn("RESP3", res3["response"])


if __name__ == "__main__":
    unittest.main(buffer=False, verbosity=2)
