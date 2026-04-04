import unittest
from unittest import mock
import importlib
import sys
import io
import contextlib
from pathlib import Path

# Ensure project root is on sys.path so package-relative imports resolve correctly
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeSerial:
    """Lightweight fake for serial.Serial used by components.Device

    - supports .open(), .close(), .write(), .read(n), .flush()
    - provides .is_open and .in_waiting properties
    """

    def __init__(self, *args, **kwargs):
        self._buffer = bytearray()
        self.is_open = False
        self.port = None
        self.baudrate = None
        self.stopbits = None
        self.parity = None
        self.bytesize = None
        self.xonxoff = False
        self.rtscts = False
        self.dsrdtr = False
        self.dtr = False
        self.rts = False

    @property
    def in_waiting(self):
        return len(self._buffer)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, data: bytes):
        # Very small dispatcher: based on command content, push response into buffer
        try:
            txt = data.decode("utf-8", errors="ignore")
        except Exception:
            txt = ""

        # strip CR/LF
        cmd = txt.strip()

        # Echo-responses for the test dict.json
        if "AT+QECHO=1" in cmd:
            self._buffer.extend(b"OK\n")
        elif "AT+CSUB" in cmd:
            self._buffer.extend(b"SubEdition: V01\n")
        else:
            # generic acknowledgement
            self._buffer.extend(b"\n")

    def read(self, n: int):
        if not self._buffer:
            return b""
        to_read = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return bytes(to_read)

    def flush(self):
        return None


class FakeDataStore:
    def __init__(self, *args, **kwargs):
        self._data = {}

    def store_data(self, device_name, variable, value):
        self._data.setdefault(device_name, {})[variable] = value

    def get_data(self, device_name, variable=None):
        if device_name not in self._data:
            return None
        if variable is None:
            return self._data[device_name].copy()
        return self._data[device_name].get(variable)

    def force_save(self):
        return None

    def stop(self):
        return None


class TestAutoComCLIWithMockDevice(unittest.TestCase):
    def setUp(self):
        # Prefer importing the real `utils` package from the repo; only create
        # lightweight fake modules if importing fails (keeps CommonUtils available)
        import importlib
        import types

        try:
            importlib.import_module("utils")
        except Exception:
            # create a minimal fake package so mock.patch("utils.dirs.get_dirs") works
            if "utils" not in sys.modules:
                sys.modules["utils"] = types.ModuleType("utils")
                # mark as package to satisfy import machinery
                setattr(sys.modules["utils"], "__path__", [])
            if "utils.dirs" not in sys.modules:
                sys.modules["utils.dirs"] = types.ModuleType("utils.dirs")
                # provide a placeholder get_dirs so mock.patch can target it without importing real utils
                setattr(sys.modules["utils.dirs"], "get_dirs", lambda: None)
                # ensure parent package exposes the submodule so mock.patch can resolve "utils.dirs"
                setattr(sys.modules["utils"], "dirs", sys.modules["utils.dirs"])

        # Ensure utils.dirs module exists before importing cli; we'll set
        # its get_dirs to return our mock `dirs` object created below.
        import importlib

        try:
            importlib.import_module("utils.dirs")
        except Exception:
            import types as _types

            ud = _types.ModuleType("utils.dirs")
            setattr(ud, "get_dirs", lambda: None)
            sys.modules["utils.dirs"] = ud

        # Provide minimal dirs object used by cli and CommandDeviceDict
        dirs = mock.Mock()
        dirs.session_dir = Path("tests/session")
        dirs.device_logs_dir = Path("tests/device_logs")
        dirs.temp_dir = Path("tests/temps")
        dirs.data_store_dir = Path("tests/data")
        dirs.get_dict_path = mock.Mock(return_value=str(Path("tests") / "dict.json"))
        dirs.get_folder_path = mock.Mock(return_value=str(Path("dicts")))
        dirs.init_project_structure = mock.Mock()
        # ensure session dir used by CommandDeviceDict is a real Path
        import time

        dirs._session_dir = dirs.device_logs_dir / time.strftime(
            "%Y-%m-%d_%H-%M-%S", time.localtime()
        )
        # patch the module-level function to return our dirs mock
        setattr(sys.modules["utils.dirs"], "get_dirs", lambda: dirs)

        # Patch DataStore to avoid background threads and file IO
        import importlib as _importlib

        _mod_ds = _importlib.import_module("components.DataStore")
        self._orig_DataStore = getattr(_mod_ds, "DataStore", None)
        setattr(_mod_ds, "DataStore", FakeDataStore)
        self.addCleanup(lambda: setattr(_mod_ds, "DataStore", self._orig_DataStore))

        # Patch serial.Serial used inside components.Device (replace Serial on the module)
        _mod_dev = _importlib.import_module("components.Device")
        _orig_serial_module = getattr(_mod_dev, "serial", None)
        if _orig_serial_module is not None and hasattr(_orig_serial_module, "Serial"):
            self._orig_serial_Serial = _orig_serial_module.Serial
            _orig_serial_module.Serial = FakeSerial
            self.addCleanup(
                lambda: setattr(_orig_serial_module, "Serial", self._orig_serial_Serial)
            )
        else:
            # Ensure at least the module defines a stub serial with Serial attr
            class _SerialStub:
                Serial = FakeSerial

            setattr(_mod_dev, "serial", _SerialStub)
            self.addCleanup(lambda: setattr(_mod_dev, "serial", _orig_serial_module))

        # Ensure real Logger is imported and configure it to write to real stderr
        import importlib as _importlib

        _mod_logger = _importlib.import_module("components.Logger")
        real_logger = _mod_logger.AutoComLogger.get_instance(
            name="AutoCom", enable_color=False
        )
        # ensure logger writes to the real stderr (bypass test capture)
        try:
            real_logger._console_handler.stream = sys.__stderr__
        except Exception:
            pass

        # Patch CommandExecutor.execute: let the real method run once, then raise KeyboardInterrupt
        import importlib

        CE = importlib.import_module("components.CommandExecutor")

        orig_execute = CE.CommandExecutor.execute
        counter = {"c": 0}

        def wrapped_execute(self, *a, **kw):
            counter["c"] += 1
            if counter["c"] == 1:
                return orig_execute(self, *a, **kw)
            raise KeyboardInterrupt

        patcher_exec = mock.patch.object(
            CE.CommandExecutor, "execute", new=wrapped_execute
        )
        patcher_exec.start()
        self.addCleanup(patcher_exec.stop)
        # expose counter for assertion
        self.mock_exec = counter

    def run_cli(self, argv):
        # import cli under the patched environment
        sys_argv_backup = sys.argv
        sys.argv = argv
        try:
            cli_mod = importlib.import_module("cli")
            importlib.reload(cli_mod)
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(
                buf_err
            ):
                try:
                    cli_mod.run_main()
                except SystemExit:
                    # expected to exit after run
                    pass

            # Print captured output directly to real stdout/stderr
            out = buf_out.getvalue()
            err = buf_err.getvalue()
            if out:
                sys.__stdout__.write(out)
            if err:
                sys.__stderr__.write(err)
        finally:
            sys.argv = sys_argv_backup

    def test_autocom_dict_infinite_with_mock_device(self):
        # Run CLI with -d tests/dict.json -i; should invoke execute_with_loop and exercise Device.send_command
        self.run_cli(["cli.py", "-d", "tests/dict.json", "-i"])

        # Verify execute was called at least once
        self.assertGreaterEqual(self.mock_exec["c"], 1)


if __name__ == "__main__":
    unittest.main()
