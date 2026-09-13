import pytest

from components.Logger import AutoComLogger
from components.TablePrinter import TablePrinter


@pytest.fixture(autouse=True)
def _cleanup_logger_instances():
    yield
    # 清理本模块创建的 logger 实例，避免跨用例干扰
    AutoComLogger._instances.pop("TestPlain", None)
    AutoComLogger._instances.pop("TestRealtime", None)


class TestLoggerIntegration:

    def _close_and_remove_file_handler(self, logger: AutoComLogger):
        # 移除并关闭文件 handler 以 flush
        fh = getattr(logger, "_file_handler", None)
        if fh:
            try:
                logger._logger.removeHandler(fh)
                fh.close()
            except Exception:
                pass

    def test_log_execution_plain_writes_concise_message(self, tmp_path):
        path = tmp_path / "plain.log"

        logger = AutoComLogger.get_instance(
            name="TestPlain", log_file=str(path), cli_output_mode="plain"
        )

        # 带 carriage return 以检查转义
        logger.log_execution(True, device="DevA", command="CMD", response="line1\r\nline2", elapsed_ms=12.34)

        self._close_and_remove_file_handler(logger)
        content = path.read_text(encoding="utf-8")

        # 期望日志里有 PASS 级别和简洁消息
        assert "PASS" in content
        assert "DevA" in content
        assert "CMD" in content
        # 转义后的 CR 应表现为 \r 或 \n 序列
        assert "\\r" in content or "\\n" in content

    def test_log_execution_realtime_writes_table(self, tmp_path):
        path = tmp_path / "realtime.log"

        logger = AutoComLogger.get_instance(
            name="TestRealtime", log_file=str(path), cli_output_mode="realtime"
        )

        # 应触发 TablePrinter 把表头和行写入文件
        logger.log_execution(False, device="DevB", command="CMD2", response="OK", elapsed_ms=1.23)

        self._close_and_remove_file_handler(logger)
        content = path.read_text(encoding="utf-8")

        # 期望表边框或表头文本存在
        assert "Executed Time" in content
        assert "Device" in content
        assert "DevB" in content


class TestTablePrinterViaLogger:

    def test_proportional_widths_sum_and_ratios(self):
        headers = ["A", "B", "C", "D", "E", "F"]
        tp = TablePrinter(headers=headers, auto_terminal=False, max_width=100, min_width=20,
                          width_mode="proportional", column_ratios=[2, 1, 1, 1, 2, 3])

        widths = tp.calculate_column_widths(mode="proportional", custom_ratios=[2,1,1,1,2,3])
        total_avail = tp.get_available_width()

        assert len(widths) == len(headers)
        assert sum(widths) == total_avail
        assert widths[0] > widths[1]
        assert widths[-1] > widths[4]
