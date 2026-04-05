import unittest
import tempfile
import json
from unittest.mock import patch
from tests.test_device import SimulatedSerial
from AutoCom import execute_with_loop


class TestAutoComCLI(unittest.TestCase):
    def test_cli_execution(self):
        # Prepare a temporary dictionary file with one device and three commands
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

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(dict_data, tf)
            tf.flush()
            dict_path = tf.name

        # Patch serial.Serial to return our SimulatedSerial instance
        with patch("components.Device.serial.Serial") as mock_serial_class:
            sim = SimulatedSerial()
            sim.is_open = True
            # Map commands to responses (include CRLF)
            sim.command_responses = {
                "CMD1": b"HELLO\r\n",
                "CMD2": b"THIS\r\n",
                "CMD3": b"AUTOCOM\r\n",
                "CMD4": b"UNKNOWN\r\n",
                "CMD5": b"ERROR\r\n",
            }
            mock_serial_class.return_value = sim

            # Call the CLI runner (one loop)
            execute_with_loop(dict_path, loop_count=3)

            # After execution, simulated serial buffer should be empty (responses consumed)
            self.assertEqual(bytes(sim._buffer), b"")


if __name__ == "__main__":
    unittest.main()
