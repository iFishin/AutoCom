import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from components.Device import Device
from tests import logger


class TestDevice(unittest.TestCase):
    def setUp(self):
        # Patch serial.Serial for all tests
        patcher = patch("components.Device.serial.Serial")
        self.addCleanup(patcher.stop)
        self.mock_serial_class = patcher.start()
        self.mock_serial = MagicMock()
        self.mock_serial.is_open = True

        # Use a plain bytearray as the serial buffer for tests
        self._serial_buffer = bytearray()

        def _read(n=1):
            if n is None:
                n = len(self._serial_buffer)
            to_read = bytes(self._serial_buffer[:n])
            del self._serial_buffer[: len(to_read)]
            return to_read

        type(self.mock_serial).in_waiting = PropertyMock(
            side_effect=lambda: len(self._serial_buffer)
        )
        self.mock_serial.read.side_effect = _read
        self.mock_serial_class.return_value = self.mock_serial

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

        def _write_side_effect(data):
            # data is bytes written to serial; strip device line ending if present
            try:
                le = getattr(self.device, "line_ending_bytes", b"\r\n")
                if le and data.endswith(le):
                    cmd_bytes = data[: -len(le)]
                else:
                    cmd_bytes = data
                cmd = cmd_bytes.decode("utf-8", errors="ignore")
            except Exception:
                cmd = ""

            resp = self.command_responses.get(cmd)
            if resp is None:
                # no response configured — do nothing
                return

            # inject response into buffer (expect bytes)
            if isinstance(resp, (bytes, bytearray)):
                self._serial_buffer[:] = resp
            elif isinstance(resp, str):
                self._serial_buffer[:] = resp.encode("utf-8")
            elif isinstance(resp, list):
                # list of strings or bytes
                parts = []
                for v in resp:
                    if isinstance(v, str):
                        parts.append(v.encode("utf-8"))
                    else:
                        parts.append(bytes(v))
                self._serial_buffer[:] = b"".join(parts)
            else:
                raise TypeError("Unsupported response type for command_responses")

        self.mock_serial.write.side_effect = _write_side_effect

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


if __name__ == "__main__":
    unittest.main(buffer=False, verbosity=2)
