import time
import threading
from concurrent.futures import ThreadPoolExecutor
try:
    from utils.common import CommonUtils
    from components.DataStore import DataStore
    from components.CommandDeviceDict import CommandDeviceDict
    from utils.ActionHandler import ActionHandler
except ModuleNotFoundError:
    from ..utils.common import CommonUtils
    from .DataStore import DataStore
    from .CommandDeviceDict import CommandDeviceDict
    from ..utils.ActionHandler import ActionHandler

class CommandExecutor:
    def __init__(self, command_device_dict, session_id=None):
        self.command_device_dict = command_device_dict
        self.data_store = DataStore(session_id=session_id)
        self.lock = threading.Lock()
        
        # Check if there is a custom ActionHandler
        action_handler_class = ActionHandler  # Default to the base class
        
        if "ConfigForActions" in command_device_dict.dict:
            handler_class_path = command_device_dict.dict["ConfigForActions"].get("handler_class")
            if handler_class_path:
                try:
                    # Dynamically import the specified handler class
                    module_path, class_name = handler_class_path.rsplit(".", 1)
                    module = __import__(module_path, fromlist=[class_name])
                    custom_handler_class = getattr(module, class_name)
                    action_handler_class = custom_handler_class
                    CommonUtils.print_log_line(f"Custom ActionHandler loaded: {handler_class_path}")
                except (ImportError, AttributeError) as e:
                    CommonUtils.print_log_line(f"Failed to load custom ActionHandler: {e}")
            
        # Create an instance of ActionHandler
        self.action_handler = action_handler_class(self)

    def execute_command(self, command) -> bool:
        self.isAllPassed = False

        def handle_variables_from_str(param):
            if CommonUtils.parse_variables_from_str(param):
                variable_name = CommonUtils.parse_variables_from_str(param)
                variable_name_dict = {}
                for var in variable_name:
                    var_value = self.data_store.get_data(device_name, var)
                    variable_name_dict[var] = var_value
                return CommonUtils.replace_variables_from_str(
                    param, variable_name, **variable_name_dict
                )
            else:
                return param

        # For backward compatibility, keep this method
        self.handle_variables_from_str = handle_variables_from_str

        device_name = command["device"]
        device = self.command_device_dict.devices[device_name]

        updated_expected_responses = []
        if "expected_responses" in command:
            for expected_response in command["expected_responses"]:
                updated_expected_responses.append(
                    handle_variables_from_str(expected_response)
                )
        
        if "command" in command:
            cmd_str = handle_variables_from_str(command["command"])
        else:
            cmd_str = ""
        
        if "parameters" in command:
            for param in command["parameters"]:
                cmd_str += handle_variables_from_str(param)
        
        if "hex_mode" in command:
            hex_mode = command["hex_mode"]
        else:
            hex_mode = False  # Default to normal mode if not specified
        
        # Call send_command with expected responses
        result = device.send_command(
            cmd_str, 
            timeout=command["timeout"] / 1000, 
            hex_mode=hex_mode,
            expected_responses=updated_expected_responses
        )
        
        # Extract response and success flag from result
        response = result["response"]
        success = result["success"]
        elapsed_time = result["elapsed_time"]
        matched = result["matched"]
        
        now = (
            time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
            + f":{int((time.time() % 1) * 1000):03d}"
        )

        # 创建上下文对象，用于传递给 ActionHandler
        context = {
            "device": device,
            "device_name": device_name,
            "cmd_str": cmd_str,
            "expected_responses": updated_expected_responses
        }

        # 调用新的 ActionHandler
        def handle_actions(command, response, action_type):
            return self.action_handler.handle_actions(command, response, action_type, context)

        # handle_response_actions 方法
        def handle_response_actions(command, response, action_type):
            return self.action_handler.handle_response_actions(command, response, action_type, context)

        # Split long strings
        cmd_lines = CommonUtils.format_long_string(cmd_str, 18)
        device_lines = CommonUtils.format_long_string(device_name, 8)
        response_preview = response[:48] + "" if len(response) > 48 else response
        response_lines = CommonUtils.format_long_string(response_preview, 48)

        if cmd_str.strip() == "":
            cmd_lines = ["ℹ INFO"]

        # Check if all expected responses matched (success flag from device)
        if success and updated_expected_responses:
            # 有期望响应且全部匹配成功
            status_msg = f"Passed ({elapsed_time:.2f}s, matched {len(matched)}/{len(updated_expected_responses)})"
            CommonUtils.print_formatted_log(
                now,
                "✅ PASS",
                device_lines[0],
                cmd_lines[0],
                status_msg,
                True,
            )
            for i in range(
                1, max(len(cmd_lines), len(response_lines), len(device_lines))
            ):
                cmd = cmd_lines[i] if i < len(cmd_lines) else ""
                resp = response_lines[i] if i < len(response_lines) else ""
                dev = device_lines[i] if i < len(device_lines) else ""
                CommonUtils.print_formatted_log("", "", dev, cmd, resp)
            CommonUtils.print_formatted_log("", "", "", "", "")
            self.isAllPassed = True
            
            # 使用新的 ActionHandler 处理 actions
            with self.lock:  # 使用锁确保原子性
                isActionPassed = all([
                    handle_actions(command, response, "success_actions"),
                    handle_response_actions(command, response, "success_response_actions"),
                    handle_response_actions(command, response, "error_response_actions")
                ])
                if not isActionPassed:
                    CommonUtils.print_log_line("❌ Action handling failed, check logs for details.")
                    CommonUtils.print_log_line("")
                
                self.isAllPassed &= isActionPassed
        elif not updated_expected_responses:
            # 没有设置期望响应,无论有无响应都算成功(超时即可)
            if response:
                status_msg = f"Got response ({elapsed_time:.2f}s)"
            else:
                status_msg = f"Completed ({elapsed_time:.2f}s)"
            
            CommonUtils.print_formatted_log(
                now,
                "✅ PASS",
                device_lines[0],
                cmd_lines[0],
                status_msg,
                True,
            )
            for i in range(
                1, max(len(cmd_lines), len(response_lines), len(device_lines))
            ):
                cmd = cmd_lines[i] if i < len(cmd_lines) else ""
                resp = response_lines[i] if i < len(response_lines) else ""
                dev = device_lines[i] if i < len(device_lines) else ""
                CommonUtils.print_formatted_log("", "", dev, cmd, resp)
            CommonUtils.print_formatted_log("", "", "", "", "")
            self.isAllPassed = True
            
            # 使用新的 ActionHandler 处理 actions
            with self.lock:
                isActionPassed = all([
                    handle_actions(command, response, "success_actions"),
                    handle_response_actions(command, response, "success_response_actions"),
                    handle_response_actions(command, response, "error_response_actions")
                ])
                if not isActionPassed:
                    CommonUtils.print_log_line("❌ Action handling failed, check logs for details.")
                    CommonUtils.print_log_line("")
                
                self.isAllPassed &= isActionPassed
        else:
            # 有期望响应但未完全匹配
            status_msg = f"Failed ({elapsed_time:.2f}s, matched {len(matched)}/{len(updated_expected_responses)})"
            
            CommonUtils.print_formatted_log(
                now,
                "❌ FAIL",
                device_lines[0],
                cmd_lines[0],
                status_msg,
                True,
            )
            for i in range(
                1, max(len(cmd_lines), len(response_lines), len(device_lines))
            ):
                cmd = cmd_lines[i] if i < len(cmd_lines) else ""
                resp = response_lines[i] if i < len(response_lines) else ""
                dev = device_lines[i] if i < len(device_lines) else ""
                CommonUtils.print_formatted_log("", "", dev, cmd, resp)
            CommonUtils.print_formatted_log("", "", "", "", "")
            self.isAllPassed = False
            
            # 使用新的 ActionHandler 处理 actions
            with self.lock:  # 使用锁确保原子性
                handle_actions(command, response, "error_actions")
                handle_response_actions(command, response, "success_response_actions")
                handle_response_actions(command, response, "error_response_actions")
        
        return self.isAllPassed

    def execute(self) -> bool:
        commands = self.command_device_dict.dict["Commands"]
        if not commands:
            CommonUtils.print_log_line("No commands to execute.")
            return

        CommonUtils.print_log_line(
            f"  {'EXECUTED_POINT':^25} | {'RESULT':^10} | {'DEVICE':^10} | {'COMMAND':^25} | {'RESPONSE':^30}  ",
            top_border=True,
            bottom_border=True,
        )

        i = 0
        self.isSinglePassed = True
        while i < len(commands):
            if commands[i].get("status") == "disabled":
                i += 1
                continue

            # Handle parallel execution strategy
            if commands[i].get("concurrent_strategy") == "parallel":
                # Collect all consecutive parallel commands
                parallel_commands = [commands[i]]
                next_idx = i + 1

                while (
                    next_idx < len(commands)
                    and commands[next_idx].get("concurrent_strategy") == "parallel"
                ):
                    parallel_commands.append(commands[next_idx])
                    next_idx += 1

                # Execute parallel commands
                result = self._execute_parallel_commands(parallel_commands)
                if not result:
                    self.isSinglePassed = False
                i = next_idx
            else:
                # Sequential execution (default behavior)
                result = self.execute_command(commands[i])
                if not result:
                    self.isSinglePassed = False
                i += 1
        return self.isSinglePassed

    def _execute_parallel_commands(self, commands) -> bool:
        # Group commands by device to avoid contention on same serial port
        device_groups = {}
        self.isParallelPassed = True
        for cmd in commands:
            device = cmd["device"]
            if device not in device_groups:
                device_groups[device] = []
            device_groups[device].append(cmd)

        # Execute commands for each device in parallel
        with ThreadPoolExecutor(max_workers=len(device_groups)) as executor:
            futures = []

            # Submit device command groups to thread pool
            for device_commands in device_groups.values():
                future = executor.submit(self._execute_device_commands, device_commands)
                futures.append(future)

            # Wait for all command groups to complete
            for future in futures:
                try:
                    result = future.result(timeout=30)
                    if not result:
                        isAllPassed = False
                except Exception as e:
                    CommonUtils.print_log_line(
                        f"Error executing parallel commands: {e}"
                    )
                    self.isParallelPassed = False
            return self.isParallelPassed

    def _execute_device_commands(self, device_commands) -> bool:
        # Execute commands for a single device sequentially
        isAllPassed = True
        for cmd in device_commands:
            if not self.execute_command(cmd):
                isAllPassed = False
        return isAllPassed