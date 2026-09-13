"""pytest 共享 fixtures。"""

import pytest

from fakes import SimulatedSerial


@pytest.fixture
def patched_serial(mocker):
    """把 `serial.Serial` 替换为 `SimulatedSerial`，返回该模拟实例。

    Device 通过 `import serial` 使用 `serial.Serial`，因此 patch `serial.Serial`
    与 patch `components.Device.serial.Serial` 等效。
    """
    mock_serial_class = mocker.patch("serial.Serial")
    sim = SimulatedSerial()
    sim.is_open = True
    mock_serial_class.return_value = sim
    return sim
