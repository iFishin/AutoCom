"""测试用的假对象（可在多个测试文件间共享）。"""


class SimulatedSerial:
    """轻量的测试用模拟串口。

    - 支持 `is_open`、`open()` / `close()`
    - 提供 `in_waiting` 属性、`read(n)`、`write(data)`、`flush()`
    - `command_responses` 可被测试用例设置为 dict
    - `_buffer` 暴露给测试以便直接注入数据
    - 可通过 `set_owner(device)` 使用设备的 `line_ending_bytes`
    """

    def __init__(self):
        self.is_open = True
        self._buffer = bytearray()
        self.command_responses = {}
        self.owner = None

    def set_owner(self, device):
        self.owner = device

    @property
    def in_waiting(self):
        return len(self._buffer)

    def read(self, n=1):
        if n is None:
            n = len(self._buffer)
        to_read = bytes(self._buffer[:n])
        del self._buffer[: len(to_read)]
        return to_read

    def write(self, data):
        try:
            le = getattr(self.owner, "line_ending_bytes", b"\r\n")
            if le and isinstance(data, (bytes, bytearray)) and data.endswith(le):
                cmd_bytes = data[: -len(le)]
            else:
                cmd_bytes = data
            cmd = (
                cmd_bytes.decode("utf-8", errors="ignore")
                if isinstance(cmd_bytes, (bytes, bytearray))
                else str(cmd_bytes)
            )
        except Exception:
            cmd = ""

        resp = self.command_responses.get(cmd)
        if resp is None:
            return

        if isinstance(resp, (bytes, bytearray)):
            self._buffer[:] = resp
        elif isinstance(resp, str):
            self._buffer[:] = resp.encode("utf-8")
        elif isinstance(resp, list):
            parts = []
            for v in resp:
                if isinstance(v, str):
                    parts.append(v.encode("utf-8"))
                else:
                    parts.append(bytes(v))
            self._buffer[:] = b"".join(parts)
        else:
            raise TypeError("Unsupported response type for command_responses")

    def flush(self):
        pass

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False
