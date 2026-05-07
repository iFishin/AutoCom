import unittest
import asyncio
import tempfile
import json
from unittest.mock import patch
from components.MCPServer import AutoComMCPServer


class SimpleSimSerial:
    def __init__(self, command_responses=None, read_chunks=None):
        self._buffer = bytearray()
        self.command_responses = command_responses or {}
        self.read_chunks = read_chunks[:] if read_chunks else []

    def write(self, data):
        try:
            # strip common CRLF endings for command matching
            if data.endswith(b"\r\n"):
                cmd_bytes = data[:-2]
            else:
                cmd_bytes = data
            cmd = cmd_bytes.decode("utf-8", errors="ignore")
        except Exception:
            cmd = ""
        resp = self.command_responses.get(cmd)
        if resp is None:
            return
        if isinstance(resp, (bytes, bytearray)):
            self._buffer[:] = resp
        elif isinstance(resp, str):
            self._buffer[:] = resp.encode("utf-8")

    def read_all(self):
        # If read_chunks provided, pop sequentially
        if self.read_chunks:
            return self.read_chunks.pop(0)
        data = bytes(self._buffer)
        self._buffer.clear()
        return data

    def close(self):
        pass


class TestMCPBusiness(unittest.TestCase):
    def test_execute_command_success(self):
        # Simulate a device that replies 'OK' to 'AT'
        sim = SimpleSimSerial(command_responses={"AT": b"OK\r\n"})
        with patch("serial.Serial") as mock_serial:
            mock_serial.return_value = sim
            res = asyncio.run(
                AutoComMCPServer._execute_command(port="COM1", command="AT", timeout=0.1)
            )
        self.assertTrue(res.get("success"))
        response = res.get("response")
        self.assertIsNotNone(response)
        assert response is not None
        self.assertIn("OK", response)

    def test_execute_commands_serial(self):
        # Serial (non-parallel) execution of multiple commands
        sim = SimpleSimSerial(command_responses={
            "CMD1": b"R1\r\n",
            "CMD2": b"R2\r\n",
            "CMD3": b"R3\r\n",
        })
        with patch("serial.Serial") as mock_serial:
            mock_serial.return_value = sim
            res = asyncio.run(
                AutoComMCPServer._execute_commands(port="COM1", commands=["CMD1", "CMD2", "CMD3"], parallel=False)
            )
        self.assertEqual(res.get("total"), 3)
        self.assertEqual(res.get("success_count"), 3)

    def test_load_dict_file(self):
        data = {"devices": [{"name": "D1"}], "commands": [{"command": "C1"}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(data, tf)
            tf.flush()
            path = tf.name
        res = asyncio.run(AutoComMCPServer._load_dict(file_path=path))
        self.assertTrue(res.get("success"))
        summary = res.get("summary")
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn("device_count", summary)

    def test_monitor_port_collects_chunks(self):
        # Provide several chunks then empty
        chunks = [b"A\r\n", b"B\r\n", b"C\r\n"]
        sim = SimpleSimSerial(read_chunks=chunks[:])
        with patch("serial.Serial") as mock_serial:
            mock_serial.return_value = sim
            res = asyncio.run(
                AutoComMCPServer._monitor_port(port="COM1", duration=0.2)
            )
        self.assertTrue(res.get("success"))
        # output should contain the concatenated chunks text
        output = res.get("output", "")
        self.assertIn("A", output)
        self.assertIn("B", output)
        self.assertIn("C", output)


if __name__ == "__main__":
    unittest.main()
