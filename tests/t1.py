# demo script to show TablePrinter output
from components.TablePrinter import TablePrinter

print("=== Full table demo ===")
printer = TablePrinter(["时间","结果","设备","命令","响应"], max_width=120, min_width=80, auto_terminal=False)
printer.add_row(["2026-04-03_11:00:00","OK","dev1","reboot","done"])
printer.add_row(["2026-04-03_11:00:01","FAIL","device_long_name","long_command_with_emoji✅","this is a very long response that should be truncated or wrapped"])
# print returned string (with borders)
print(printer.print_table(top_border=True, bottom_border=True, is_print=False))

print("\n=== Realtime demo ===")
rt = TablePrinter(["T","R"], max_width=60, min_width=30, auto_terminal=False)
rt.print_realtime_row(["t1","r1"], is_print=True)
rt.print_realtime_row(["t2","r2"], is_print=True)
rt.print_realtime_banner("This is a banner")
rt.print_realtime_row(["t3","r3"], is_print=True)
rt.print_realtime_row(["t4","r4"], is_print=True)
