import threading
import unittest
from types import SimpleNamespace

from components.CommandExecutor import CommandExecutor
from utils.ActionHandler import ActionHandler


class _FakeDevice:
    def __init__(self, response=None):
        self.calls = []
        self._response = response or {
            "success": True,
            "response": "OK",
            "elapsed_time": 0.01,
            "matched": ["OK"],
        }

    def send_command(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, "kwargs": kwargs})
        return self._response


class _FakeActionHandler:
    def handle_actions(self, command, response, action_type, context):
        _ = (command, response, action_type, context)
        return True

    def handle_response_actions(self, command, response, action_type, context):
        _ = (command, response, action_type, context)
        return True


class _FakeDataStore:
    def store_data(self, *_args, **_kwargs):
        return None


class _FakeExecutor:
    def __init__(self, command_device_dict):
        self.command_device_dict = command_device_dict
        self.data_store = _FakeDataStore()
        self.isAllPassed = False


class TestCommandOptionsPassthrough(unittest.TestCase):
    def test_execute_command_passes_monitor_options(self):
        fake_device = _FakeDevice()
        executor = CommandExecutor.__new__(CommandExecutor)
        executor.lock = threading.Lock()
        executor.data_store = _FakeDataStore()
        executor.defer_response_actions = False
        executor.deferred_response_actions = []
        executor.action_handler = _FakeActionHandler()
        executor.command_device_dict = SimpleNamespace(
            devices={"DeviceA": fake_device},
            device_monitors={"DeviceA": object()},
        )
        executor._handle_response_actions_with_defer = lambda *args, **kwargs: True
        executor.handle_variables_from_str = (
            lambda param, device_name=None: param
        )

        cmd = {
            "device": "DeviceA",
            "command": "AT+QVERSION",
            "expected_responses": ["OK"],
            "timeout": 1000,
            "priority": 7,
            "completion_rules": {
                "expected_required": True,
                "terminal_patterns": ["OK", "ERROR"],
                "idle_timeout": 0.5,
            },
        }

        ok = executor.execute_command(cmd)

        self.assertTrue(ok)
        self.assertEqual(len(fake_device.calls), 1)
        sent = fake_device.calls[0]
        self.assertEqual(sent["cmd"], "AT+QVERSION")
        self.assertEqual(sent["kwargs"]["priority"], 7)
        self.assertIn("completion_rules", sent["kwargs"])
        self.assertTrue(sent["kwargs"]["completion_rules"]["expected_required"])

    def test_retry_passes_monitor_options(self):
        fake_device = _FakeDevice(
            response={
                "success": True,
                "response": "OK",
                "elapsed_time": 0.01,
                "matched": ["OK"],
            }
        )
        command_device_dict = SimpleNamespace(device_monitors={"DeviceA": object()})
        executor = _FakeExecutor(command_device_dict)
        action_handler = ActionHandler(executor)

        command = {
            "device": "DeviceA",
            "timeout": 1000,
            "hex_mode": False,
            "priority": 3,
            "completion_rules": {"expected_required": True},
        }
        context = {
            "device": fake_device,
            "device_name": "DeviceA",
            "cmd_str": "AT",
            "expected_responses": ["OK"],
            "priority": 3,
            "completion_rules": {"expected_required": True},
        }

        ok = action_handler.handle_retry(1, command, "", context)

        self.assertTrue(ok)
        self.assertEqual(len(fake_device.calls), 1)
        sent = fake_device.calls[0]
        self.assertEqual(sent["kwargs"]["priority"], 3)
        self.assertTrue(sent["kwargs"]["completion_rules"]["expected_required"])


if __name__ == "__main__":
    unittest.main()
