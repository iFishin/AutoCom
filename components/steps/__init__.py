"""AutoCom Step Handlers — 每种 step type 对应一个 Handler"""

from .base import BaseStepHandler, StepResult
from .serial import SerialStepHandler, SerialWaitStepHandler
from .http import HttpStepHandler
from .script import ScriptStepHandler
from .wait import WaitStepHandler
from .action_batch import ActionBatchStepHandler

__all__ = [
    "BaseStepHandler", "StepResult",
    "SerialStepHandler",
    "SerialWaitStepHandler",
    "HttpStepHandler",
    "ScriptStepHandler",
    "WaitStepHandler",
    "ActionBatchStepHandler",
]

BUILTIN_HANDLERS = {
    "serial": SerialStepHandler,
    "serial_wait": SerialWaitStepHandler,
    "http": HttpStepHandler,
    "script": ScriptStepHandler,
    "wait": WaitStepHandler,
    "action_batch": ActionBatchStepHandler,
}
