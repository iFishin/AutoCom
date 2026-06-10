import threading
import time
import unittest

from components.CommandDeviceDict import CommandDeviceDict, MonitorManager


class _FakeSerialNoRead:
    def __init__(self):
        self.in_waiting = 128
        self.read_called = False
        self.written = []

    def read(self, _n):
        self.read_called = True
        return b""

    def write(self, data):
        self.written.append(data)

    def flush(self):
        return None


class _FakeDevice:
    def __init__(self):
        self.lock = threading.Lock()
        self.line_ending_bytes = b"\r\n"
        self.ser = _FakeSerialNoRead()
        self.logged = []

    def write_to_log(self, line):
        self.logged.append(line)

    def _parse_hex_command(self, command):
        return bytes.fromhex(command)


class _FakeMonitor:
    def __init__(self):
        self.command_lock = threading.Lock()
        self._data = []
        self._active = False
        self._wait_calls = 0
        self._slot_lock = threading.Lock()

    def acquire_command_slot(self, priority=0):
        _ = priority
        self._slot_lock.acquire()

    def release_command_slot(self):
        if self._slot_lock.locked():
            self._slot_lock.release()

    def begin_command_capture(self):
        self._active = True
        self._data = []

    def wait_for_command_response(self, _timeout):
        # Simulate data arriving during the first polling cycle.
        self._wait_calls += 1
        if self._wait_calls == 1 and self._active:
            self._data.append("OK")
            return True
        return False

    def get_command_capture_snapshot(self):
        return list(self._data)

    def end_command_capture(self):
        self._active = False
        return list(self._data)


class _FakeMonitorDevice:
    def __init__(self):
        self.ser = type("S", (), {"is_open": True})()
        self.log_file = None


class TestCommandDeviceDictMonitor(unittest.TestCase):
    def test_send_command_with_monitor_does_not_clear_serial_buffer(self):
        cdd = CommandDeviceDict.__new__(CommandDeviceDict)
        device_name = "DebugA"
        fake_device = _FakeDevice()
        fake_monitor = _FakeMonitor()

        cdd.devices = {device_name: fake_device}
        cdd.device_monitors = {device_name: fake_monitor}

        response = cdd.send_command_with_monitor(
            device_name=device_name,
            command="AT",
            timeout=0.3,
            hex_mode=False,
            expected_responses=["OK"],
            original_send_command=lambda *args, **kwargs: "unused",
        )

        self.assertFalse(
            fake_device.ser.read_called,
            "monitor mode should not read/clear serial buffer in send path",
        )
        self.assertTrue(fake_device.ser.written)
        self.assertIn("OK", response)

    def test_monitor_capture_snapshot_keeps_all_lines(self):
        monitor = MonitorManager(_FakeMonitorDevice(), "DebugA", "unused")

        monitor.begin_command_capture()
        monitor._process_line("LINE1")
        monitor._process_line("LINE2")
        snapshot = monitor.get_command_capture_snapshot()
        final_data = monitor.end_command_capture()

        self.assertEqual(snapshot, ["LINE1", "LINE2"])
        self.assertEqual(final_data, ["LINE1", "LINE2"])

    def test_priority_queue_allows_high_priority_to_overtake_waiting_normal(self):
        monitor = MonitorManager(_FakeMonitorDevice(), "DebugA", "unused")
        order = []

        def worker(name, priority, hold=0.0, start_delay=0.0):
            if start_delay:
                time.sleep(start_delay)
            monitor.acquire_command_slot(priority=priority)
            try:
                order.append(name)
                if hold:
                    time.sleep(hold)
            finally:
                monitor.release_command_slot()

        t1 = threading.Thread(target=worker, args=("normal-1", 0, 0.12, 0.0))
        t2 = threading.Thread(target=worker, args=("normal-2", 0, 0.0, 0.01))
        t3 = threading.Thread(target=worker, args=("high", 10, 0.0, 0.02))

        t1.start()
        t2.start()
        t3.start()
        t1.join()
        t2.join()
        t3.join()

        self.assertEqual(order[0], "normal-1")
        self.assertEqual(order[1], "high")
        self.assertEqual(order[2], "normal-2")

    def test_completion_rules_expected_required(self):
        response_lines = ["AT+PING", "OK"]

        should_finish, reason, _ = CommandDeviceDict._should_finish_command(
            response_lines=response_lines,
            expected_responses=["+PING:OK"],
            completion_rules={"expected_required": True},
            terminal_seen_time=None,
            now=time.time(),
            settle_after_terminal=0.01,
        )
        self.assertFalse(should_finish)
        self.assertEqual(reason, "terminal-seen-awaiting-expected")

        should_finish2, reason2, _ = CommandDeviceDict._should_finish_command(
            response_lines=["AT+PING", "+PING:OK"],
            expected_responses=["+PING:OK"],
            completion_rules={"expected_required": True},
            terminal_seen_time=None,
            now=time.time(),
            settle_after_terminal=0.01,
        )
        self.assertTrue(should_finish2)
        self.assertEqual(reason2, "expected-matched")


if __name__ == "__main__":
    unittest.main()
