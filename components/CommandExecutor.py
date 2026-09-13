"""
CommandExecutor — 命令执行器（兼容层 + 新架构入口）

保持向后兼容的同时，内部改用 PipelineScheduler 驱动 Steps 执行。
"""

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any, Optional

from utils.common import CommonUtils
from components.DataStore import DataStore
from components.CommandDeviceDict import CommandDeviceDict
from utils.ActionHandler import ActionHandler
from components.Logger import get_logger, AutoComLogger
from components.SessionStore import SessionStore
from components.Context import Context
from components.PipelineScheduler import PipelineScheduler
from components.steps import BUILTIN_HANDLERS
from utils.dirs import get_dirs

logger: AutoComLogger = get_logger("AutoCom")


class CommandExecutor:
    """命令执行器。

    兼容旧代码：仍暴露 data_store / execute_command() API。
    但内部用 PipelineScheduler + Step Handlers 驱动。
    """

    def __init__(
        self,
        command_device_dict_or_dict,
        session_id=None,
        context: Optional[Context] = None,
    ):
        self.lock = threading.Lock()
        self.context = context  # 可能为 None，在 _ensure_context() 中创建

        # ── 旧 DataStore 兼容层 ──

        # 后台命令执行队列（旧系统保留）
        self.deferred_command_queue = Queue()
        self.deferred_execution_thread = None

        # 迭代追踪信息
        self.current_iteration = None
        self.total_iterations = None

        # 并行执行期间的延迟 actions 收集
        self.defer_response_actions = False
        self.deferred_response_actions = []

        # 从执行配置文件数据中获取数据
        dict_data = (
            command_device_dict_or_dict
            if isinstance(command_device_dict_or_dict, dict)
            else command_device_dict_or_dict.dict
        )

        # ── 处理 Constants（写入 Context 或旧 DataStore） ──
        self._process_constants(dict_data)

        # ── 创建 CommandDeviceDict（打开串口） ──
        if isinstance(command_device_dict_or_dict, dict):
            self.command_device_dict = CommandDeviceDict(
                command_device_dict_or_dict,
                self._compat_data_store(),
            )
        else:
            self.command_device_dict = command_device_dict_or_dict
            if self.command_device_dict._data_store is None:
                self.command_device_dict._data_store = self._compat_data_store()

        # ── 注入 Device 实例到 Context ──
        ctx = self._ensure_context()
        for name, dev in self.command_device_dict.devices.items():
            ctx.set(f"_runtime.devices.{name}", dev)
            # 同时记录设备元信息
            ctx.set(f"devices.{name}.port", getattr(dev, "port", ""))
            ctx.set(f"devices.{name}.baud_rate", getattr(dev, "baud_rate", 115200))

        # ── 创建 ActionHandler ──
        self.action_handler = self._create_action_handler(dict_data)

        # ── 创建 Step Handlers ──
        self.step_handlers = {}
        ctx = self._ensure_context()
        for stype, handler_cls in BUILTIN_HANDLERS.items():
            self.step_handlers[stype] = handler_cls(ctx, self.action_handler)

        # ── 创建 PipelineScheduler ──
        self.scheduler: Optional[PipelineScheduler] = None

        # 启动后台命令执行线程（旧系统保留）
        self._start_deferred_execution_thread()

    # ── 属性兼容 ──

    @property
    def data_store(self):
        """旧代码通过 data_store 读写变量 → 统一走 Context。"""
        return self._compat_data_store()

    @data_store.setter
    def data_store(self, value):
        """测试兼容：允许外部直接注入 mock DataStore。"""
        self._legacy_data_store = value

    @property
    def ctx(self) -> Context:
        """新代码统一用 ctx。"""
        return self._ensure_context()

    # ── 内部：Context 懒初始化 ──

    def _ensure_context(self) -> Context:
        """如果外部未传入 Context，自动创建一个（standalone 模式）。"""
        if not hasattr(self, "context") or self.context is None:
            from components.SessionStore import SessionStore

            store = SessionStore(get_dirs().db_path)
            sid = time.strftime("%Y-%m-%d_%H%M%S")
            store.create_session(sid, config_name="standalone")
            self.context = Context(store, sid)
        return self.context

    def _compat_data_store(self):
        """返回兼容的 DataStore/Context 对象。

        Context 支持 store_data/get_data 兼容 API，完全替代旧 DataStore。
        """
        return self._ensure_context()

    def handle_variables_from_str(self, param, device_name=None):
        """兼容旧 ActionHandler 的 {VAR} 变量替换入口。"""
        if isinstance(param, str):
            return CommonUtils.process_variables(
                param, self._compat_data_store(), device_name
            )
        return param

    # ── 常量处理 ──

    def _process_constants(self, dict_data: dict):
        if "Constants" not in dict_data:
            return

        need_input = []
        for key, value in dict_data["Constants"].items():
            val = str(value) if value is not None else ""
            if val == "":
                need_input.append(key)
            else:
                self._compat_data_store().store_data("Constants", key, val)

        # 需要用户输入的常量
        if need_input:
            logger.log_session_start("The following constants need your input:")
            for key in need_input:
                for attempt in range(3):
                    try:
                        val = input(f"Please enter value for {key}: ").strip()
                        if not val:
                            if attempt < 2:
                                logger.log_session_start(
                                    f"Value cannot be empty. Please try again ({attempt + 1}/3)"
                                )
                                continue
                            else:
                                logger.log_session_start(
                                    f"No valid value provided for {key}"
                                )
                                sys.exit(1)
                        self._compat_data_store().store_data("Constants", key, val)
                        break
                    except KeyboardInterrupt:
                        logger.log_session_start("\n❌ Input cancelled by user")
                        sys.exit(1)

    # ── ActionHandler 创建 ──

    def _create_action_handler(self, dict_data: dict) -> ActionHandler:
        handler_class = ActionHandler
        if "ConfigForActions" in dict_data:
            class_path = dict_data["ConfigForActions"].get("handler_class")
            if class_path:
                try:
                    mod_path, cls_name = class_path.rsplit(".", 1)
                    module = __import__(mod_path, fromlist=[cls_name])
                    handler_class = getattr(module, cls_name)
                    logger.log_session_start(
                        f"Custom ActionHandler loaded: {class_path}"
                    )
                except (ImportError, AttributeError) as e:
                    logger.log_session_start(
                        f"Failed to load custom ActionHandler: {e}"
                    )
        return handler_class(self)

    # ── 旧 execute_command 保留（向后兼容） ──

    def execute_command(self, command) -> bool:
        """保留原 execute_command 方法，供旧 action handler 调用。

        内部仍走旧的 device.send_command 逻辑。
        """
        self.isAllPassed = False

        device_name = command["device"]
        device = self.command_device_dict.devices[device_name]

        updated_expected_responses = []
        if "expected_responses" in command:
            for expected_response in command["expected_responses"]:
                updated_expected_responses.append(
                    self.handle_variables_from_str(expected_response, device_name)
                )

        if "command" in command:
            cmd_str = self.handle_variables_from_str(command["command"], device_name)
        else:
            cmd_str = ""

        if "parameters" in command:
            for param in command["parameters"]:
                cmd_str += self.handle_variables_from_str(param, device_name)

        hex_mode = command.get("hex_mode", False)
        priority = self._resolve_priority(command, device_name)
        completion_rules = self._resolve_completion_rules(command, device_name)

        send_args = {
            "timeout": command["timeout"] / 1000,
            "hex_mode": hex_mode,
            "expected_responses": updated_expected_responses,
        }
        if self._supports_monitor_send_options(device_name):
            send_args["priority"] = priority
            send_args["completion_rules"] = completion_rules

        result = device.send_command(cmd_str, **send_args)
        response = result["response"]
        success = result["success"]
        elapsed_time = result["elapsed_time"]
        matched = result["matched"]

        context = {
            "device": device,
            "device_name": device_name,
            "cmd_str": cmd_str,
            "expected_responses": updated_expected_responses,
            "priority": priority,
            "completion_rules": completion_rules,
        }

        response_preview = response[:48] + "..." if len(response) > 48 else response
        if cmd_str.strip() == "":
            cmd_str = "ℹ INFO"

        if success and updated_expected_responses:
            logger.log_execution(
                time_str=time.strftime("%Y-%m-%d_%H:%M:%S"),
                result=True,
                device=device_name,
                command=cmd_str,
                response=response_preview,
                elapsed_ms=elapsed_time * 1000,
            )
            self.isAllPassed = True
            with self.lock:
                is_ok = all(
                    [
                        self.action_handler.handle_actions(
                            command, response, "success_actions", context
                        ),
                        self._handle_response_actions_with_defer(
                            command, response, "success_response_actions", context
                        ),
                        self.action_handler.handle_response_actions(
                            command, response, "error_response_actions", context
                        ),
                    ]
                )
                self.isAllPassed = self.isAllPassed and is_ok
        elif not updated_expected_responses:
            logger.log_execution(
                time_str=time.strftime("%Y-%m-%d_%H:%M:%S"),
                result=True,
                device=device_name,
                command=cmd_str,
                response=response_preview,
                elapsed_ms=elapsed_time * 1000,
            )
            self.isAllPassed = True
            with self.lock:
                is_ok = all(
                    [
                        self.action_handler.handle_actions(
                            command, response, "success_actions", context
                        ),
                        self._handle_response_actions_with_defer(
                            command, response, "success_response_actions", context
                        ),
                        self.action_handler.handle_response_actions(
                            command, response, "error_response_actions", context
                        ),
                    ]
                )
                self.isAllPassed = self.isAllPassed and is_ok
        else:
            logger.log_execution(
                time_str=time.strftime("%Y-%m-%d_%H:%M:%S"),
                result=False,
                device=device_name,
                command=cmd_str,
                response=response_preview,
                elapsed_ms=elapsed_time * 1000,
            )
            self.isAllPassed = False
            with self.lock:
                self.action_handler.handle_actions(
                    command, response, "error_actions", context
                )
                self._handle_response_actions_with_defer(
                    command, response, "success_response_actions", context
                )
                self.action_handler.handle_response_actions(
                    command, response, "error_response_actions", context
                )

        return self.isAllPassed

    # ── 新 execute：走 PipelineScheduler ──

    def execute(self) -> bool:
        """执行所有步骤（新架构：走 PipelineScheduler）。"""
        dict_data = self.command_device_dict.dict

        # Commands → Steps 自动转换
        if "Steps" not in dict_data and "Commands" in dict_data:
            dict_data["Steps"] = PipelineScheduler._convert_commands(
                dict_data["Commands"]
            )

        steps = dict_data.get("Steps", [])
        if not steps:
            logger.log_session_start("No steps to execute.")
            return False

        # 自动给缺失 device 的 step 赋值为唯一设备
        devices = self.command_device_dict.devices
        if devices and len(devices) == 1:
            only_dev_name = next(iter(devices))
            for s in steps:
                if "device" not in s:
                    s["device"] = only_dev_name

        # 标记迭代
        ctx = self._ensure_context()
        if self.current_iteration is not None:
            ctx.set("session.iteration", self.current_iteration)
            ctx.set("session.total", self.total_iterations or 0)
            for device_name, device in self.command_device_dict.devices.items():
                device.mark_iteration(self.current_iteration, self.total_iterations)

        # 创建调度器
        self.scheduler = PipelineScheduler(
            steps=steps,
            ctx=ctx,
            handlers=self.step_handlers,
            action_handler=self.action_handler,
        )

        # 执行
        result = self.scheduler.run()

        # 等待延迟命令执行完成
        self._wait_for_deferred_commands()

        # 标记本轮执行结果到设备日志
        if self.current_iteration is not None:
            for device_name, device in self.command_device_dict.devices.items():
                device.end_iteration(
                    self.current_iteration,
                    success=result,
                    total_iterations=self.total_iterations,
                )

        return result

    # ── 以下为旧系统保留方法 ──

    def _supports_monitor_send_options(self, device_name):
        monitors = getattr(self.command_device_dict, "device_monitors", {})
        return device_name in monitors

    def _resolve_priority(self, command, device_name):
        raw = command.get("priority", 0)
        resolved = self.handle_variables_from_str(raw, device_name)
        try:
            return int(resolved)
        except (ValueError, TypeError):
            return 0

    def _resolve_completion_rules(self, command, device_name):
        raw_rules = command.get("completion_rules")
        if not raw_rules:
            return None

        def _resolve(value):
            if isinstance(value, str):
                return self.handle_variables_from_str(value, device_name)
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            return value

        return _resolve(raw_rules)

    def set_iteration_info(self, current_iteration, total_iterations=None):
        self.current_iteration = current_iteration
        self.total_iterations = total_iterations

    def _start_deferred_execution_thread(self):
        self.deferred_execution_thread = threading.Thread(
            target=self._deferred_execution_worker, daemon=False
        )
        self.deferred_execution_thread.start()

    def _deferred_execution_worker(self):
        while True:
            try:
                item = self.deferred_command_queue.get(timeout=1)
                if item is None:
                    self.deferred_command_queue.task_done()
                    break
                try:
                    self.execute_command(item)
                except Exception as e:
                    logger.log_step_error(f"Error executing deferred command: {e}")
                finally:
                    self.deferred_command_queue.task_done()
            except:  # Queue.Empty
                continue

    def enqueue_deferred_command(self, command):
        self.deferred_command_queue.put(command)

    def _handle_response_actions_with_defer(
        self, command, response, action_type, context
    ):
        if self.defer_response_actions:
            self.deferred_response_actions.append(
                (command, response, action_type, context)
            )
            return True
        return self.action_handler.handle_response_actions(
            command, response, action_type, context
        )

    def _wait_for_deferred_commands(self):
        self.deferred_command_queue.join()

    def _execute_deferred_response_actions(self):
        if not self.deferred_response_actions:
            return
        actions = self.deferred_response_actions.copy()
        self.deferred_response_actions.clear()
        for item in actions:
            try:
                if (
                    isinstance(item, dict)
                    and item.get("action_type") == "deferred_execute"
                ):
                    self.execute_command(item["command"])
                else:
                    command, response, action_type, context = item
                    self.action_handler.handle_response_actions(
                        command, response, action_type, context
                    )
            except Exception as e:
                logger.log_step_error(f"❌ Error processing deferred action: {e}")

    def shutdown(self):
        """关闭后台执行线程并关闭 Context。"""
        try:
            self.deferred_command_queue.join()
        except Exception:
            pass
        try:
            self.deferred_command_queue.put(None)
        except Exception:
            pass
        if self.deferred_execution_thread and self.deferred_execution_thread.is_alive():
            try:
                self.deferred_execution_thread.join(timeout=5)
            except Exception:
                pass
        # 关闭 Context
        if self.context is not None:
            try:
                self.context.close_session("completed")
            except Exception as e:
                logger.log_session_error(f"Error closing context: {e}")
                pass
