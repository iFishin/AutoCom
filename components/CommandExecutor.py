import time
import threading
import sys
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
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
    def __init__(self, command_device_dict_or_dict, session_id=None):
        # 创建 DataStore 实例
        self.data_store = DataStore(session_id=session_id)
        self.lock = threading.Lock()
        
        # 后台命令执行队列（用于处理 success_response_actions 中的嵌套命令）
        self.deferred_command_queue = Queue()
        self.deferred_execution_thread = None
        
        # 迭代追踪信息
        self.current_iteration = None
        self.total_iterations = None
        
        # 并行执行期间的延迟 actions 收集（避免在并行期间干扰串口通信）
        self.defer_response_actions = False  # 标志：是否延迟处理 execute_command_by_order
        self.deferred_response_actions = []  # 收集延迟的 (command, response, action_type, context)
        
        # 从字典数据中获取数据
        dict_data = command_device_dict_or_dict if isinstance(command_device_dict_or_dict, dict) else command_device_dict_or_dict.dict
        
        # 处理常量
        if "Constants" in dict_data:
            need_input_constants = []
            loaded_constants = []

            for key, value in dict_data["Constants"].items():
                if value == "":  # 空字符串，需要用户输入
                    need_input_constants.append(key)
                else:
                    self.data_store.store_data("Constants", key, value)
                    loaded_constants.append(key)

            # 处理需要用户输入的常量
            if need_input_constants:
                CommonUtils.print_log_line(
                    "The following constants need your input:",
                    top_border=True,
                )
                
                for key in need_input_constants:
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            # 提示用户输入并去除首尾空格
                            value = input(f"Please enter value for {key}: ").strip()
                            
                            if not value:  # 如果输入为空
                                if attempt < max_retries - 1:
                                    CommonUtils.print_log_line(f"Value cannot be empty. Please try again ({attempt + 1}/{max_retries})")
                                    continue
                                else:
                                    CommonUtils.print_log_line(f"❌ No valid value provided for {key} after {max_retries} attempts")
                                    sys.exit(1)
                            
                            # 存储用户输入的值
                            self.data_store.store_data("Constants", key, value)
                            CommonUtils.print_log_line(f"✓ Stored {key} = {value}")
                            break
                            
                        except KeyboardInterrupt:
                            CommonUtils.print_log_line("\n❌ Input cancelled by user")
                            sys.exit(1)
                        except Exception as e:
                            if attempt < max_retries - 1:
                                CommonUtils.print_log_line(f"Error: {e}. Please try again ({attempt + 1}/{max_retries})")
                                continue
                            else:
                                CommonUtils.print_log_line(f"❌ Failed to get value for {key} after {max_retries} attempts: {e}")
                                sys.exit(1)
                
                CommonUtils.print_log_line(
                    f"✓ Successfully collected values for all {len(need_input_constants)} constants",
                    bottom_border=True,
                )

        # 创建或更新 CommandDeviceDict
        if isinstance(command_device_dict_or_dict, dict):
            self.command_device_dict = CommandDeviceDict(command_device_dict_or_dict, self.data_store)
        else:
            self.command_device_dict = command_device_dict_or_dict
            # 注入 DataStore 实例到现有的 CommandDeviceDict
            if self.command_device_dict._data_store is None:
                self.command_device_dict._data_store = self.data_store
        
        # Check if there is a custom ActionHandler
        action_handler_class = ActionHandler  # Default to the base class
        
        if "ConfigForActions" in self.command_device_dict.dict:
            handler_class_path = self.command_device_dict.dict["ConfigForActions"].get("handler_class")
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
        
        # 启动后台命令执行线程
        self._start_deferred_execution_thread()
    
    def _start_deferred_execution_thread(self):
        """启动后台线程处理延迟执行的命令（避免嵌套锁导致的死锁）"""
        self.deferred_execution_thread = threading.Thread(
            target=self._deferred_execution_worker,
            daemon=False
        )
        self.deferred_execution_thread.start()
    
    def _deferred_execution_worker(self):
        """后台线程工作函数，处理延迟执行的命令"""
        while True:
            try:
                item = self.deferred_command_queue.get(timeout=1)
                if item is None:  # Sentinel value to stop the thread
                    self.deferred_command_queue.task_done()
                    break
                
                cmd = item
                try:
                    self.execute_command(cmd)
                except Exception as e:
                    CommonUtils.print_log_line(f"❌ Error executing deferred command: {e}")
                finally:
                    self.deferred_command_queue.task_done()
                    
            except:  # Queue.Empty exception
                continue
    
    def enqueue_deferred_command(self, command):
        """将命令加入后台执行队列，避免嵌套锁死锁"""
        self.deferred_command_queue.put(command)
    
    def _handle_response_actions_with_defer(self, command, response, action_type, context):
        """处理 response_actions，在并行执行期间延迟所有响应处理"""
        # 如果在并行执行期间，收集所有响应处理，包括 retry，稍后统一执行
        if self.defer_response_actions:
            self.deferred_response_actions.append((command, response, action_type, context))
            return True
        
        # 不在并行执行期间，直接处理
        def handle_response_actions(command, response, action_type):
            return self.action_handler.handle_response_actions(command, response, action_type, context)
        return handle_response_actions(command, response, action_type)

    def execute_command(self, command) -> bool:
        self.isAllPassed = False

        # For backward compatibility, keep this method
        def handle_variables_from_str(param, device_name):
            if isinstance(param, str):
                # 尝试从 Constants 和设备变量中获取变量值
                result = CommonUtils.process_variables(param, self.data_store, device_name)
                return result
            return param
            
        self.handle_variables_from_str = handle_variables_from_str

        device_name = command["device"]
        device = self.command_device_dict.devices[device_name]

        updated_expected_responses = []
        if "expected_responses" in command:
            for expected_response in command["expected_responses"]:
                updated_expected_responses.append(
                    handle_variables_from_str(expected_response, device_name)
                )
        
        if "command" in command:
            cmd_str = handle_variables_from_str(command["command"], device_name)
        else:
            cmd_str = ""
        
        if "parameters" in command:
            for param in command["parameters"]:
                cmd_str += handle_variables_from_str(param, device_name)
        
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

        # Prepare command display string
        response_preview = response[:48] + "" if len(response) > 48 else response

        if cmd_str.strip() == "":
            cmd_str = "ℹ INFO"

        # Check if all expected responses matched (success flag from device)
        if success and updated_expected_responses:
            # 有期望响应且全部匹配成功
            status_msg = f"Passed ({elapsed_time:.2f}s, matched {len(matched)}/{len(updated_expected_responses)})"
            CommonUtils.print_formatted_log(
                now,
                "✅ PASS",
                device_name,
                cmd_str,
                status_msg,
                False,
            )
            self.isAllPassed = True
            
            # 使用新的 ActionHandler 处理 actions
            with self.lock:  # 使用锁确保原子性
                isActionPassed = all([
                    handle_actions(command, response, "success_actions"),
                    self._handle_response_actions_with_defer(command, response, "success_response_actions", context),
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
                device_name,
                cmd_str,
                status_msg,
                False,
            )
            self.isAllPassed = True
            
            # 使用新的 ActionHandler 处理 actions
            with self.lock:
                isActionPassed = all([
                    handle_actions(command, response, "success_actions"),
                    self._handle_response_actions_with_defer(command, response, "success_response_actions", context),
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
                device_name,
                cmd_str,
                status_msg,
                False,
            )
            self.isAllPassed = False
            
            # 使用新的 ActionHandler 处理 actions
            with self.lock:  # 使用锁确保原子性
                handle_actions(command, response, "error_actions")
                self._handle_response_actions_with_defer(command, response, "success_response_actions", context)
                handle_response_actions(command, response, "error_response_actions")
        
        return self.isAllPassed
    
    def set_iteration_info(self, current_iteration, total_iterations=None):
        """Set iteration information for logging purposes
        
        Args:
            current_iteration: Current iteration number (1-based)
            total_iterations: Total number of iterations (optional)
        """
        self.current_iteration = current_iteration
        self.total_iterations = total_iterations

    def execute(self) -> bool:
        commands = self.command_device_dict.dict["Commands"]
        if not commands:
            CommonUtils.print_log_line("No commands to execute.")
            return False

        # Mark iteration in all device logs if iteration info is set
        if self.current_iteration is not None:
            for device_name, device in self.command_device_dict.devices.items():
                device.mark_iteration(self.current_iteration, self.total_iterations)

        # Print table header
        CommonUtils.print_formatted_log(
            time_str="Time",
            result="Result",
            device="Device",
            command_str="Command",
            response_str="Response",
            first_line=True,
            top_border=True,
            bottom_border=True
        )
        
        i = 0
        self.isSinglePassed = True
        while i < len(commands):
            # 在处理任何命令前，检查是否有延迟的 response actions 需要执行
            # 这确保触发的命令在适当的时机执行，不会打断并行块
            if not commands[i].get("concurrent_strategy") == "parallel" and self.deferred_response_actions:
                self._execute_deferred_response_actions()
            
            if commands[i].get("status") == "disabled":
                i += 1
                continue

            # Handle parallel execution strategy
            if commands[i].get("concurrent_strategy") == "parallel":
                # Collect all consecutive parallel commands with the same order
                current_order = commands[i].get("order")
                parallel_commands = [commands[i]]
                next_idx = i + 1

                while (
                    next_idx < len(commands)
                    and commands[next_idx].get("concurrent_strategy") == "parallel"
                    and commands[next_idx].get("order") == current_order
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
        
        # 等待所有延迟执行的命令完成
        self._wait_for_deferred_commands()
        
        return self.isSinglePassed
    
    def _wait_for_deferred_commands(self):
        """等待所有延迟执行的命令完成"""
        # 将所有后台队列中的命令执行完毕
        self.deferred_command_queue.join()
    
    def shutdown(self):
        """关闭后台执行线程"""
        try:
            # 首先等待队列中所有任务完成（最多等待 10 秒）
            self.deferred_command_queue.join()
        except Exception as e:
            CommonUtils.print_log_line(f"Warning: Error while waiting for deferred commands: {e}")
        
        # 发送停止信号
        try:
            self.deferred_command_queue.put(None)  # Sentinel value
        except Exception as e:
            CommonUtils.print_log_line(f"Warning: Error while sending stop signal to deferred execution thread: {e}")
        
        # 等待线程退出（最多等待 5 秒）
        if self.deferred_execution_thread and self.deferred_execution_thread.is_alive():
            try:
                self.deferred_execution_thread.join(timeout=5)
                if self.deferred_execution_thread.is_alive():
                    CommonUtils.print_log_line("Warning: Deferred execution thread did not terminate within 5 seconds")
            except Exception as e:
                CommonUtils.print_log_line(f"Warning: Error while joining deferred execution thread: {e}")

    def _execute_parallel_commands(self, commands) -> bool:
        # Group commands by device to avoid contention on same serial port
        device_groups = {}
        self.isParallelPassed = True
        for cmd in commands:
            device = cmd["device"]
            if device not in device_groups:
                device_groups[device] = []
            device_groups[device].append(cmd)

        # 在并行执行期间，延迟处理 execute_command_by_order，避免打乱并行流程
        previous_defer_state = self.defer_response_actions
        self.defer_response_actions = True
        # 不要清空列表，因为可能有来自之前并行块的延迟命令，只在执行时才清空

        try:
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
                            self.isParallelPassed = False
                    except Exception as e:
                        CommonUtils.print_log_line(
                            f"Error executing parallel commands: {e}"
                        )
                        self.isParallelPassed = False
        finally:
            # 并行执行完毕后，恢复之前的延迟状态
            self.defer_response_actions = previous_defer_state
            
            # 不在这里执行延迟 actions，而是留到主循环中的适当时机
            # （在执行下一个非并行指令前执行，以避免打断后续的并行块）
            
        return self.isParallelPassed

    def _execute_device_commands(self, device_commands) -> bool:
        # Execute commands for a single device sequentially
        isAllPassed = True
        for cmd in device_commands:
            if not self.execute_command(cmd):
                isAllPassed = False
        return isAllPassed
    
    def _execute_deferred_response_actions(self):
        """执行所有延迟的 execute_command_by_order 操作"""
        if not self.deferred_response_actions:
            return
        
        # 保存当前的延迟列表，然后清空它
        actions_to_execute = self.deferred_response_actions.copy()
        self.deferred_response_actions.clear()
        
        for item in actions_to_execute:
            try:
                # 处理两种格式：新格式（字典）和旧格式（元组）
                if isinstance(item, dict) and item.get("action_type") == "deferred_execute":
                    # 新格式：直接执行命令
                    cmd = item["command"]
                    self.execute_command(cmd)
                else:
                    # 旧格式：处理响应操作
                    command, response, action_type, context = item
                    self.action_handler.handle_response_actions(command, response, action_type, context)
            except Exception as e:
                CommonUtils.print_log_line(f"❌ Error processing deferred action: {e}")