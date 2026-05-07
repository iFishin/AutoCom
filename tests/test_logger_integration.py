import os
import tempfile
import unittest

from components.Logger import AutoComLogger
from components.TablePrinter import TablePrinter


class LoggerIntegrationTests(unittest.TestCase):

    def tearDown(self) -> None:
        # Cleanup any created logger instances to avoid cross-test interference
        AutoComLogger._instances.pop("TestPlain", None)
        AutoComLogger._instances.pop("TestRealtime", None)

    def _close_and_remove_file_handler(self, logger: AutoComLogger):
        # remove file handler and close it to flush
        fh = getattr(logger, "_file_handler", None)
        if fh:
            try:
                logger._logger.removeHandler(fh)
                fh.close()
            except Exception:
                pass

    def test_log_execution_plain_writes_concise_message(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        path = tmp.name

        logger = AutoComLogger.get_instance(
            name="TestPlain", log_file=path, cli_output_mode="plain"
        )

        # include a carriage return to check escaping
        logger.log_execution(True, device="DevA", command="CMD", response="line1\r\nline2", elapsed_ms=12.34)

        # flush and close
        self._close_and_remove_file_handler(logger)

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        os.unlink(path)

        # Expect level PASS in the formatted log and the concise message
        self.assertIn("PASS", content)
        self.assertIn("DevA", content)
        self.assertIn("CMD", content)
        # escaped CR should appear as \r or \n sequences in our escaped handling
        self.assertTrue("\\r" in content or "\\n" in content)

    def test_log_execution_realtime_writes_table(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        path = tmp.name

        logger = AutoComLogger.get_instance(
            name="TestRealtime", log_file=path, cli_output_mode="realtime"
        )

        # This should cause TablePrinter to write header + row into file
        logger.log_execution(False, device="DevB", command="CMD2", response="OK", elapsed_ms=1.23)

        # remove handler to flush
        self._close_and_remove_file_handler(logger)

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        os.unlink(path)

        # Expect table borders or header text present
        self.assertIn("Executed Time", content)
        self.assertIn("Device", content)
        # data row should contain device name
        self.assertIn("DevB", content)


class TablePrinterTests(unittest.TestCase):

    def test_proportional_widths_sum_and_ratios(self):
        headers = ["A", "B", "C", "D", "E", "F"]
        tp = TablePrinter(headers=headers, auto_terminal=False, max_width=100, min_width=20,
                          width_mode="proportional", column_ratios=[2, 1, 1, 1, 2, 3])

        widths = tp.calculate_column_widths(mode="proportional", custom_ratios=[2,1,1,1,2,3])
        total_avail = tp.get_available_width()

        # lengths match headers and sum equals available width (approx)
        self.assertEqual(len(widths), len(headers))
        self.assertEqual(sum(widths), total_avail)

        # check relative ordering by ratios (first should be larger than second)
        self.assertGreater(widths[0], widths[1])
        self.assertGreater(widths[-1], widths[4])


if __name__ == "__main__":
    unittest.main()
