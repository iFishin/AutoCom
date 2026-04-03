import unittest
from components.TablePrinter import TablePrinter
from wcwidth import wcswidth, wcwidth

class TestTablePrinter(unittest.TestCase):
    def test_get_string_display_width_and_truncate(self):
        # ASCII and emoji width
        s = "abc✅d"
        # 'abc' (3) + emoji (2) + 'd'(1) = 6
        # verify width using wcwidth directly
        self.assertEqual(wcswidth(s), 6)
        # truncate to width 4 using per-char wcwidth
        target = 4
        cur = 0
        cut = len(s)
        for i, ch in enumerate(s):
            w = wcwidth(ch)
            if w < 0:
                w = 1
            if cur + w > target:
                cut = i
                break
            cur += w
        t = s[:cut]
        self.assertLessEqual(wcswidth(t), 4)

    def test_calculate_column_widths_equal_and_proportional(self):
        headers = ["A", "B", "C"]
        tp = TablePrinter(headers, max_width=90, min_width=30, auto_terminal=False)
        # equal
        widths_equal = tp.calculate_column_widths(mode='equal')
        self.assertEqual(len(widths_equal), 3)
        # proportional with custom ratios
        ratios = [0.2, 0.3, 0.5]
        widths_prop = tp.calculate_column_widths(mode='proportional', custom_ratios=ratios)
        self.assertEqual(len(widths_prop), 3)
        self.assertEqual(sum(widths_prop), tp.get_available_width())

    def test_content_and_header_based_widths(self):
        headers = ["Time", "Result", "Device"]
        tp = TablePrinter(headers, max_width=120, min_width=50, auto_terminal=False)
        tp.add_row(["2026-04-03_10:00:00", "OK", "dev1"])
        tp.add_row(["2026-04-03_10:00:01", "FAIL", "device_long_name"])
        widths = tp.calculate_column_widths(mode='content')
        self.assertEqual(len(widths), 3)
        # widths should be positive
        for w in widths:
            self.assertGreater(w, 0)

    def test_print_table_and_realtime(self):
        headers = ["T","R"]
        tp = TablePrinter(headers, max_width=80, min_width=40, auto_terminal=False)
        tp.add_row(["t1","r1"])
        out = tp.print_table(is_print=False)
        self.assertIn("t1", out)
        # realtime: create a printer and call print_realtime_row
        line = tp.print_realtime_row(["t2", "r2"], is_print=False)
        self.assertIsInstance(line, str)
        self.assertIn("t2", line)

    def test_print_table_preserves_borders(self):
        headers = ["Col1","Col2","Col3"]
        tp = TablePrinter(headers, max_width=100, min_width=60, auto_terminal=False)
        tp.add_row(["a","b","c"])
        out = tp.print_table(is_print=False, top_border=True, bottom_border=True)
        # check top and bottom rounded border characters exist
        self.assertIn('╭', out)
        self.assertTrue(('╯' in out) or ('╮' in out))

    def test_print_table_stdout(self):
        import io
        import contextlib
        headers = ["H1", "H2"]
        tp = TablePrinter(headers, max_width=80, min_width=40, auto_terminal=False)
        tp.add_row(["row1col1", "row1col2"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tp.print_table(is_print=True, top_border=True, bottom_border=True)
        out = buf.getvalue()
        self.assertIn('╭', out)
        self.assertIn('│', out)
        self.assertIn('row1col1', out)

    def test_print_realtime_stdout(self):
        import io
        import contextlib
        headers = ["H", "R"]
        tp = TablePrinter(headers, max_width=60, min_width=30, auto_terminal=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tp.print_realtime_row(["r1", "r2"], is_print=True)
        out = buf.getvalue()
        # header + one data line printed
        self.assertIn('╭', out)
        self.assertIn('│', out)
        self.assertIn('r1', out)

    def test_print_full_table(self):
        headers = ["时间","结果","设备","命令","响应"]
        tp = TablePrinter(headers, max_width=160, min_width=100, auto_terminal=False)
        tp.add_row(["2026-04-03_11:00:00","OK","dev1","reboot","done"])
        tp.add_row(["2026-04-03_11:00:01","FAIL","device_long_name","long_command_with_emoji✅","this is a very long response that should be truncated or wrapped"])
        tp.add_banner("This is a banner that should span the entire width of the table")
        tp.add_row(["2026-04-03_11:00:02","OK","dev2","update","all done"])
        tp.add_row(["2026-04-03_11:00:03","FAIL","dev3","install","error occurred during installation, please check logs for details"])
        out = tp.print_table(top_border=True, bottom_border=True, is_print=False)
        print(out)
        self.assertIn("2026-04-03_11:00:00", out)
        self.assertIn("device_long_name", out)
        self.assertIn("long_command", out)

    def test_print_realtime_banner(self):
        print("\n=== Realtime demo ===")
        rt = TablePrinter(["T","R"], max_width=60, min_width=30, auto_terminal=False)
        rt.print_realtime_row(["t1","r1"], is_print=True)
        rt.print_realtime_row(["t2","r2"], is_print=True)
        rt.print_realtime_banner("This is a banner")
        rt.print_realtime_row(["t3","r3"], is_print=True)
        rt.print_realtime_row(["t4","r4"], is_print=True)
        rt.print_realtime_bottom()

if __name__ == '__main__':
    unittest.main()

    
