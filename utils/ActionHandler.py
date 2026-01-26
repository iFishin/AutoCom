import re
import time
import random
import string
try:
    from utils.common import CommonUtils
except ModuleNotFoundError:
    from .common import CommonUtils

class ActionHandler:
    """
    处理命令执行过程中的各种 actions
    用户可以通过继承此类添加自定义 action 处理方法
    """
    
    def __init__(self, executor):
        """
        初始化 ActionHandler
        
        Args:
            executor: CommandExecutor 实例的引用，用于访问数据存储和其他资源
        """
        self.executor = executor
        # 自动发现所有以 handle_ 开头的处理方法
        self.handlers = self._discover_handlers()
        CommonUtils.print_log_line(f"Registered {len(self.handlers)} action handlers")
        
    def _discover_handlers(self):
        """自动发现所有处理方法并映射到对应的 action 类型"""
        handlers = {}
        for attr_name in dir(self):
            if attr_name.startswith('handle_') and callable(getattr(self, attr_name)) and attr_name != 'handle_actions' and attr_name != 'handle_response_actions':
                # 从方法名提取 action 类型，例如 handle_save -> save
                action_type = attr_name[len('handle_'):]
                handlers[action_type] = getattr(self, attr_name)
        return handlers
    
    def handle_variables_from_str(self, param):
        """处理字符串中的变量引用"""
        if hasattr(self.executor, 'handle_variables_from_str'):
            return self.executor.handle_variables_from_str(param, self.last_device_name if hasattr(self, 'last_device_name') else None)
        return param
    
    def safe_store_data(self, device_name, variable, value):
        """
        安全地存储数据，带有错误处理和验证
        
        Args:
            device_name: 设备名称
            variable: 变量名
            value: 要存储的值
            
        Returns:
            bool: True 如果存储成功，False 如果失败
        """
        try:
            if not device_name or not variable:
                CommonUtils.print_log_line(f"❌ Invalid storage parameters: device='{device_name}', variable='{variable}'")
                return False
            
            self.executor.data_store.store_data(device_name, variable, value)
            
            # 验证数据是否成功存储
            stored_value = self.executor.data_store.get_data(device_name, variable)
            if stored_value != value:
                CommonUtils.print_log_line(f"⚠️ Warning: Stored value verification failed for {device_name}.{variable}")
                return False
                
            return True
        except Exception as e:
            CommonUtils.print_log_line(f"❌ Error storing data to {device_name}.{variable}: {e}")
            return False
        
    def handle_actions(self, command, response, action_type, context):
        """
        处理一组 actions
        
        Args:
            command: 当前命令对象
            response: 命令执行的响应
            action_type: 要处理的 action 类型 (success_actions, error_actions 等)
            context: 执行上下文，包含设备、命令字符串等
            
        Returns:
            bool: True 如果所有操作成功，否则 False
        """
        if action_type not in command:
            return True  # 没有要处理的 action，视为成功
        
        actions = command[action_type]
        result = True
        
        # 保存当前设备名
        if 'device_name' in context:
            self.last_device_name = context['device_name']
        
        for action in actions:
            try:
                # 查找动作类型及其处理器
                found = False
                for key, value in action.items():
                    if key in self.handlers:
                        # 找到了处理器，调用对应方法
                        # CommonUtils.print_log_line(f"Processing action: {key}")
                        handler_result = self.handlers[key](value, command, response, context)
                        if handler_result is False:  # 明确返回 False 表示失败
                            result = False
                        found = True
                        break
                        
                if not found:
                    # 找不到处理方法
                    CommonUtils.print_log_line(f"Unknown action type: {action}")
                    result = False
                    
            except Exception as e:
                device_name = context.get('device_name', 'Unknown')
                device = context.get('device')
                port_info = f" (port: {device.port})" if device and hasattr(device, 'port') else ""
                CommonUtils.print_log_line(f"Error occurred while processing action on device '{device_name}'{port_info}: {e}")
                result = False
                
        return result
    
    def handle_response_actions(self, command, response, action_type, context):
        """处理响应触发的 actions"""
        if action_type not in command:
            return True
        
        actions = command[action_type]
        result = True
        
        if isinstance(actions, dict):
            # success_response_actions 或 error_response_actions 格式（键为匹配条件，值为 actions 列表）
            for key, action_list in actions.items():
                if key in response:
                    CommonUtils.print_log_line(f"ℹ Response contains `{key}`")
                    CommonUtils.print_log_line("")
                    # 对每个 action 进行处理
                    for action in action_list:
                        try:
                            found = False
                            for action_key, value in action.items():
                                if action_key in self.handlers:
                                    # 直接调用处理器
                                    handler_result = self.handlers[action_key](value, command, response, context)
                                    if handler_result is False:
                                        result = False
                                    found = True
                                    break
                            
                            if not found:
                                CommonUtils.print_log_line(f"Unknown action type: {action}")
                                result = False
                        except Exception as e:
                            device_name = context.get('device_name', 'Unknown')
                            device = context.get('device')
                            port_info = f" (port: {device.port})" if device and hasattr(device, 'port') else ""
                            CommonUtils.print_log_line(f"Error processing response action on device '{device_name}'{port_info}: {e}")
                            result = False
        elif isinstance(actions, list):
            # 简单的 actions 列表格式
            return self.handle_actions({"temp_actions": actions}, response, "temp_actions", context)
        
        return result
    
    
    # ---------------------------------------------------------
    # 以下是各种 action 的具体处理方法
    # ---------------------------------------------------------
    
    def handle_test(self, text, command, response, context):
        """
        测试功能

        用法:
        {
            "test": "test_message"
        }
        """
        test_message = self.handle_variables_from_str(text)
        CommonUtils.print_log_line(f"ℹ Test action executed with message: {test_message}")
        CommonUtils.print_log_line("")
        return True

    def handle_save(self, config, command, response, context):
        """
        保存数据功能

        用法:
        {
            "save": {
                "device": "device_name",
                "variable": "variable_name",
                "value": "value_to_save"
            }
        }
        """
        device_name = self.handle_variables_from_str(config["device"])
        variable = self.handle_variables_from_str(config["variable"])
        value = self.handle_variables_from_str(config["value"])
        
        CommonUtils.print_log_line(
            f"ℹ Saving data from response to {device_name}.{variable}"
        )
        CommonUtils.print_log_line("")
        
        return self.safe_store_data(device_name, variable, value)

    def handle_save_conditional(self, config, command, response, context):
        """
        条件保存数据功能

        用法:
        {
            "save_conditional": {
                "device": "device_name",
                "variable": "variable_name",
                "pattern": "regex_pattern"
            }
        }
        """
        device_name = self.handle_variables_from_str(config["device"])
        variable = self.handle_variables_from_str(config["variable"])
        
        CommonUtils.print_log_line(
            f"ℹ Saving data from response to {device_name}.{variable} if condition is met"
        )
        CommonUtils.print_log_line("")
        
        if "pattern" in config:
            match = re.search(config["pattern"], response)
            if match:
                value = match.group(1)
                return self.safe_store_data(device_name, variable, value)
            else:
                CommonUtils.print_log_line(
                    f"Warning: Pattern '{config['pattern']}' not found in response"
                )
                CommonUtils.print_log_line("")
                return False
        else:
            return self.safe_store_data(device_name, variable, response)

    def handle_retry(self, retry_times, command, response, context):
        """
        重试命令功能

        用法:
        {
            "retry": retry_times
        }
        """
        device = context["device"]
        cmd_str = context["cmd_str"]
        updated_expected_responses = context["expected_responses"]

        CommonUtils.print_log_line(
            f"Starting retry operation, will retry {command['command']} {retry_times} times..."
        )
        CommonUtils.print_log_line("")

        for attempt in range(retry_times):
            CommonUtils.print_log_line(
                f"Retry attempt {attempt + 1}/{retry_times}"
            )
            CommonUtils.print_log_line("")

            # Get hex_mode from command if available
            hex_mode = command.get("hex_mode", False)
            
            # Call send_command with new signature
            result = device.send_command(
                cmd_str, 
                timeout=command["timeout"] / 1000,
                hex_mode=hex_mode,
                expected_responses=updated_expected_responses
            )
            
            # Extract response text from result dictionary
            response_text = result["response"]
            success = result["success"]

            if success:
                CommonUtils.print_log_line(
                    f"✅ Retry {command['command']} successful!"
                )
                CommonUtils.print_log_line("")

                # 处理成功时的 actions
                new_context = context.copy()
                new_context["response"] = response_text
                self.handle_actions(command, response_text, "success_actions", new_context)

                self.executor.isAllPassed = True
                return True
            else:
                CommonUtils.print_log_line(
                    "❌ Retry failed, trying again..."
                    if attempt < retry_times - 1
                    else "❌ All retries failed!"
                )
                CommonUtils.print_log_line("")
                self.executor.isAllPassed = False

        return False

    def handle_set_status(self, status, command, response, context):
        """
        设置状态功能

        用法:
        {
            "set_status": "status_value"
        }
        """
        CommonUtils.print_log_line(
            f"ℹ Setting status of command with order {command['order']} to {status}"
        )
        CommonUtils.print_log_line("")
        command["status"] = status
        return True

    def handle_wait(self, wait_action, command, response, context):
        """
        等待功能

        用法:
        {
            "wait": {
                "duration": wait_time_in_milliseconds
            }
        }
        """
        if isinstance(wait_action, dict):
            duration = float(wait_action.get("duration", 1))
        else:
            duration = float(wait_action)

        CommonUtils.print_log_line(f"ℹ Waiting for {duration} milliseconds")
        CommonUtils.print_log_line("")
        time.sleep(duration/1000)
        return True

    def handle_print(self, message, command, response, context):
        """
        打印消息功能

        用法:
        {
            "print": "message_to_print"
        }
        """
        print_action = "ℹ  " + message
        CommonUtils.print_log_line(
            self.handle_variables_from_str(print_action)
        )
        CommonUtils.print_log_line("")
        return True

    def handle_set_status_by_order(self, config, command, response, context):
        """
        通过序号设置状态功能

        用法:
        {
            "set_status_by_order": {
                "order": command_order,
                "status": "status_value"
            }
        }
        """
        order = config.get("order")
        status = config.get("status")
        CommonUtils.print_log_line(
            f"ℹ Setting status of command with order {order} to {status}"
        )
        CommonUtils.print_log_line("")

        for cmd in self.executor.command_device_dict.dict["Commands"]:
            if cmd["order"] == order:
                cmd["status"] = status
                break
        return True

    def handle_execute_command(self, config, command, response, context):
        """
        执行命令功能

        用法:
        {
            "execute_command": {
                "command": "command_string",
                "timeout": timeout_in_milliseconds
            }
        }
        """
        device = context["device"]

        CommonUtils.print_log_line(
            f"ℹ Executing command: {config['command']}"
        )
        CommonUtils.print_log_line("")

        # Get hex_mode from config if available
        hex_mode = config.get("hex_mode", False)
        
        # Call send_command with new signature (no expected_responses for execute_command)
        result = device.send_command(
            self.handle_variables_from_str(config["command"]),
            timeout=config["timeout"] / 1000,
            hex_mode=hex_mode
        )
        return True

    def handle_execute_command_by_order(self, order, command, response, context):
        """
        通过序号执行命令功能

        用法:
        {
            "execute_command_by_order": command_order
        }
        
        注意: 在并行执行期间，此命令会被延迟到并行执行完毕后执行，
        以避免在多设备并行通信时干扰响应匹配。
        """
        CommonUtils.print_log_line(
            f"ℹ Executing command with order {order}"
        )
        CommonUtils.print_log_line("")

        for cmd in self.executor.command_device_dict.dict["Commands"]:
            if cmd["order"] == order:
                # 检查是否在并行执行期间
                if self.executor.defer_response_actions:
                    # 在并行执行期间，收集此 action，稍后执行
                    self.executor.deferred_response_actions.append((command, response, "success_response_actions", context))
                else:
                    # 不在并行执行期间，直接执行
                    self.executor.enqueue_deferred_command(cmd)
                break
        return True

    def handle_generate_random_str(self, config, command, response, context):
        """
        生成随机字符串功能

        用法:
        {
            "generate_random_str": {
                "device": "device_name",
                "variable": "variable_name",
                "length": string_length
            }
        }
        """
        if "length" in config:
            length = config["length"]
        else:
            length = random.randint(10, 120)

        random_str = "".join(
            random.choices(
                string.ascii_letters + string.digits, k=length
            )
        )

        device_name = self.handle_variables_from_str(config["device"])
        variable = self.handle_variables_from_str(config["variable"])
        
        return self.safe_store_data(device_name, variable, random_str)

    def handle_calculate_length(self, config, command, response, context):
        """
        计算字符串长度功能

        用法:
        {
            "calculate_length": {
                "device": "device_name",
                "variable": "variable_name",
                "data": "string_to_calculate"
            }
        }
        """
        data = self.handle_variables_from_str(config["data"])
        length = len(data)

        device_name = self.handle_variables_from_str(config["device"])
        variable = self.handle_variables_from_str(config["variable"])
        
        return self.safe_store_data(device_name, variable, length)

    def handle_calculate_crc(self, config, command, response, context):
        """
        计算 CRC 功能

        用法:
        {
            "calculate_crc": {
                "device": "device_name",
                "variable": "variable_name",
                "raw_data": "data_to_calculate_crc"
            }
        }
        """
        raw_data = self.handle_variables_from_str(config["raw_data"])
        crc = 0

        for i in range(len(raw_data)):
            crc += ord(raw_data[i]) + i + 1

        device_name = self.handle_variables_from_str(config["device"])
        variable = self.handle_variables_from_str(config["variable"])
        
        return self.safe_store_data(device_name, variable, crc)

    def handle_replace_str(self, config, command, response, context):
        """
        替换字符串功能

        用法:
        {
            "replace_str": {
                "device": "device_name",
                "variable": "variable_name",
                "data": "original_string",
                "original_str": "string_to_replace",
                "new_str": "replacement_string"
            }
        }
        """
        data = self.handle_variables_from_str(config["data"])
        original_str = self.handle_variables_from_str(config["original_str"])
        new_str = self.handle_variables_from_str(config["new_str"])

        replaced_data = data.replace(original_str, new_str)

        device_name = self.handle_variables_from_str(config["device"])
        variable = self.handle_variables_from_str(config["variable"])
        
        return self.safe_store_data(device_name, variable, replaced_data)
    
    def handle_wifi_connect(self, config, command, response, context):
        """
        连接 WiFi 功能

        用法:
        {
            "wifi_connect": {
                "ssid": "SSID",
                "password": "password",
                "timeout": 10  # 可选参数，连接超时时间(秒)
            }
        }
        """
        import time
        import pywifi
        from pywifi import const

        ssid = self.handle_variables_from_str(config["ssid"])
        password = self.handle_variables_from_str(config["password"])
        timeout = int(config.get("timeout", 10))  # 默认10秒超时

        CommonUtils.print_log_line(f"ℹ Connecting to WiFi network: {ssid}")

        try:
            # Initialize WiFi
            wifi = pywifi.PyWiFi()
            
            # Get the first wireless interface
            iface = wifi.interfaces()[0]
            
            # Disconnect current connection
            iface.disconnect()
            time.sleep(1)
            
            # Create WiFi connection profile
            profile = pywifi.Profile()
            profile.ssid = ssid
            profile.auth = const.AUTH_ALG_OPEN
            profile.akm.append(const.AKM_TYPE_WPA2PSK)
            profile.cipher = const.CIPHER_TYPE_CCMP
            profile.key = password
            
            # Remove all WiFi profiles
            iface.remove_all_network_profiles()
            
            # Add new profile
            profile_added = iface.add_network_profile(profile)
            
            # Connect to WiFi
            CommonUtils.print_log_line("Attempting to connect...")
            iface.connect(profile_added)
            
            # Wait for connection success or timeout
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = iface.status()
                if status == const.IFACE_CONNECTED:
                    CommonUtils.print_log_line(f"✅ Successfully connected to WiFi network: {ssid}")
                    CommonUtils.print_log_line("")
                    return True
                time.sleep(0.5)
            
            # Timeout without connection
            CommonUtils.print_log_line(f"❌ Connection to WiFi timed out, please check if the SSID and password are correct")
            return False
            
        except Exception as e:
            CommonUtils.print_log_line(f"❌ Error occurred while connecting to WiFi: {e}")
            return False
        
    def handle_get_wifi_config(self, config, command, response, context):
        """
        发送WiFi配置到指定设备IP (通过GET请求)

        用法:
        {
            "get_wifi_config": {
                "device_ip": "192.168.88.1",
                "ssid": "MyWiFi",
                "password": "MyPassword"
            }
        }
        """
        import requests
        import time

        # 获取并处理参数
        device_ip = self.handle_variables_from_str(config["device_ip"])
        ssid = self.handle_variables_from_str(config["ssid"])
        password = self.handle_variables_from_str(config["password"])

        # 构建目标URL
        config_url = f"http://{device_ip}/connect?ssid={ssid}&pass={password}&submit=Submit"

        CommonUtils.print_log_line(f"ℹ Sending WiFi configuration to device {device_ip}")
        CommonUtils.print_log_line(f"  Target URL: {config_url}")

        try:
            # 第一次发送WiFi配置
            try:
                requests.get(config_url, timeout=5)
                CommonUtils.print_log_line(f"ℹ First WiFi configuration request sent successfully!")
            except Exception as e:
                CommonUtils.print_log_line(f"ℹ First request encountered an error.")
                CommonUtils.print_log_line(f"ℹ Proceeding to wait and retry...")

            # 等待10秒
            CommonUtils.print_log_line(f"ℹ Waiting for 15 seconds before sending the second request...")
            time.sleep(15)

            # 第二次发送WiFi配置
            response = requests.get(config_url, timeout=5)
            if response.status_code == 200:
                CommonUtils.print_log_line(f"✅ Second WiFi configuration request successful!")
                CommonUtils.print_log_line("")
                return True
            else:
                CommonUtils.print_log_line(f"❌ Second WiFi configuration request failed with status code: {response.status_code}")
                CommonUtils.print_log_line("")
                return False
            
        except Exception as e:
            CommonUtils.print_log_line(f"❌ Error occurred while sending WiFi configuration: {str(e)}")
            CommonUtils.print_log_line("")
            return False

    def handle_get_network_page(self, config, command, response, context):
        """
        获取网络页面内容 (通过GET请求)

        用法:
        {
            "get_network_page": {
                "device_ip": "192.168.19.1",
                "url": "/"
            }
        }
        """
        import requests

        # 获取并处理参数
        device_ip = self.handle_variables_from_str(config["device_ip"])
        url = self.handle_variables_from_str(config["url"])

        # 构建目标URL
        target_url = f"http://{device_ip}{url}"

        CommonUtils.print_log_line(f"ℹ Fetching network page content from {target_url}")

        try:
            response = requests.get(target_url, timeout=5)
            if response.status_code == 200:
                CommonUtils.print_log_line(f"✅ Successfully fetched network page content!")
                CommonUtils.print_log_line("")
                return True
            else:
                CommonUtils.print_log_line(f"❌ Failed to fetch network page content, status code: {response.status_code}")
                CommonUtils.print_log_line("")
                return False
            
        except Exception as e:
            CommonUtils.print_log_line(f"❌ Error occurred while fetching network page: {str(e)}")
            CommonUtils.print_log_line("")
            return False
    
    def handle_send_file(self, config, command, response, context):
        """
        向设备串口发送文本文件功能（支持证书、配置文件等）

        用法:
        {
            "send_file": "certs/server.crt"
        }

        或使用 dict 格式，指定编码和行结束符:
        {
            "send_file": {
                "path": "certs/server.crt",
                "encoding": "utf-8",
                "line_ending": "lf"
            }
        }

        参数说明:
        - path: 文本文件路径，支持相对路径（基于当前工作目录 os.getcwd()）或绝对路径
        - encoding: 可选，文件编码方式，默认为 'utf-8'，可选 'gbk'、'latin-1' 等
        - line_ending: 可选，行结束符转换规则，默认为 'lf'
          * 'lf': 使用 LF（\\n，0x0a），Unix/Linux/Mac 风格
          * 'crlf': 使用 CRLF（\\r\\n，0x0d0a），Windows 风格
          * 'cr': 使用 CR（\\r，0x0d），旧 Mac 风格
          * 'none': 保持原样，不做转换

        行为:
        - 以文本模式读取文件，使用指定编码转换为字符串
        - 标准化行结束符（CRLF/LF/CR 都转为 LF）
        - 根据 line_ending 参数转换为目标格式
        - 将转换后的内容通过设备串口发送，记录原始大小和实际写入大小
        - 在设备日志中记录文件名、原始大小、写入大小和转换格式

        返回:
        - True: 发送成功
        - False: 文件不存在、串口未打开或发送失败

        示例场景（发送证书）:
        {
            "send_file": {
                "path": "certs/certificate.pem",
                "encoding": "utf-8",
                "line_ending": "lf"
            }
        }
        """
        import os

        # Resolve file path from config
        if isinstance(config, str):
            file_path = config
            encoding = "utf-8"
            line_ending = "lf"
        elif isinstance(config, dict):
            file_path = config.get("path")
            encoding = config.get("encoding", "utf-8")
            line_ending = config.get("line_ending", "lf")
        else:
            CommonUtils.print_log_line("Error: invalid send_file config")
            return False

        file_path = self.handle_variables_from_str(file_path)

        # If path is relative, base it on current working directory
        if not os.path.isabs(file_path):
            cwd = os.getcwd()
            file_path = os.path.join(cwd, file_path)

        # Find device from context
        device = context.get("device") if context else None
        device_name = context.get("device_name") if context else None

        if not device:
            CommonUtils.print_log_line(f"Error: device not provided in action context for send_file ({file_path})")
            return False

        # Read text file
        try:
            with open(file_path, "r", encoding=encoding) as f:
                text_content = f.read()
        except FileNotFoundError:
            CommonUtils.print_log_line(f"Error: file not found: {file_path}")
            return False
        except UnicodeDecodeError as e:
            CommonUtils.print_log_line(f"Error: encoding error when reading '{file_path}' with {encoding}: {e}")
            return False
        except Exception as e:
            CommonUtils.print_log_line(f"Error reading file '{file_path}': {e}")
            return False

        original_size = len(text_content.encode(encoding))

        # Normalize line endings: convert all CRLF/CR to LF first
        normalized_content = text_content.replace("\r\n", "\n").replace("\r", "\n")

        # Convert to target line ending format
        if line_ending.lower() == "crlf":
            final_content = normalized_content.replace("\n", "\r\n")
        elif line_ending.lower() == "cr":
            final_content = normalized_content.replace("\n", "\r")
        elif line_ending.lower() == "none":
            final_content = text_content  # Keep original as-is
        else:  # "lf" or default
            final_content = normalized_content

        # Convert to bytes
        try:
            data = final_content.encode(encoding)
        except Exception as e:
            CommonUtils.print_log_line(f"Error encoding content for '{file_path}': {e}")
            return False

        # Write to serial port
        try:
            written = 0
            with device.lock:
                if not (hasattr(device, 'ser') and getattr(device.ser, 'is_open', False)):
                    CommonUtils.print_log_line(f"Serial port not open for device '{device_name or device.name}', cannot send file: {file_path}")
                    return False

                # PySerial's write returns number of bytes written
                written = device.ser.write(data)
                try:
                    device.ser.flush()
                except Exception:
                    # flush may not be supported on some transports
                    pass

            CommonUtils.print_log_line(f"Sent file '{os.path.basename(file_path)}' to device '{device_name or device.name}': original_size={original_size} bytes, written={written} bytes, encoding={encoding}, line_ending={line_ending}")

            # Also write to device log if available
            try:
                timestamp = device._get_timestamp() if hasattr(device, '_get_timestamp') else time.strftime("%Y-%m-%d_%H:%M:%S")
            except Exception:
                # Best-effort logging to device file
                pass

            return True
        except Exception as e:
            CommonUtils.print_log_line(f"Error sending file to device '{device_name or getattr(device, 'name', 'Unknown')}': {e}")
            return False