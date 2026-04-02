import unittest
from unittest.mock import patch, MagicMock
from components.Device import Device

class TestDevice(unittest.TestCase):
    def setUp(self):
        # Patch serial.Serial for all tests
        patcher = patch('components.Device.serial.Serial')
        self.addCleanup(patcher.stop)
        self.mock_serial_class = patcher.start()
        self.mock_serial = MagicMock()
        self.mock_serial.is_open = True
        self.mock_serial.in_waiting = 0
        self.mock_serial.read.return_value = b''
        self.mock_serial_class.return_value = self.mock_serial

        # Patch CommonUtils.print_log_line to avoid print
        patcher_utils = patch('components.Device.CommonUtils')
        self.addCleanup(patcher_utils.stop)
        self.mock_utils = patcher_utils.start()
        self.mock_utils.force_decode.side_effect = lambda b: b.decode('utf-8', errors='ignore')

        self.device = Device(
            name='TestDevice',
            port='COM1',
            baud_rate=9600
        )

    def test_init_success(self):
        self.assertEqual(self.device.name, 'TestDevice')
        self.assertEqual(self.device.port, 'COM1')
        self.assertTrue(self.device.ser.is_open)
        self.assertFalse(self.device.open_failed)

    def test_send_command_success(self):
        self.mock_serial.in_waiting = 1
        self.mock_serial.read.return_value = b'OK\n'
        result = self.device.send_command('AT', timeout=0.1, expected_responses=['OK'])
        self.assertTrue(result['success'])
        self.assertIn('OK', result['response'])
        self.assertIn('OK', result['matched'])

    def test_send_command_no_response(self):
        self.mock_serial.in_waiting = 0
        result = self.device.send_command('AT', timeout=0.05, expected_responses=['OK'])
        self.assertFalse(result['success'])
        self.assertEqual(result['matched'], [])

    def test_setup_logging_and_close(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = self.device.setup_logging(tmpdir)
            self.assertTrue(log_path.endswith('.log'))
            self.device.close()
            self.assertTrue(self.device.shutdown_flag)

    def test_get_status(self):
        status = self.device.get_status()
        self.assertEqual(status['name'], 'TestDevice')
        self.assertEqual(status['port'], 'COM1')
        self.assertIn('serial_open', status)

if __name__ == '__main__':
    unittest.main()
