import serial
import time
import json
import threading
import os
import re
import queue
import sys
import argparse

# 根据运行方式选择导入路径
try:
    from utils.common import CommonUtils
    from components.CommandDeviceDict import CommandDeviceDict
    from components.CommandExecutor import CommandExecutor
    from version import __version__
except ModuleNotFoundError:
    from .utils.common import CommonUtils
    from .components.CommandDeviceDict import CommandDeviceDict
    from .components.CommandExecutor import CommandExecutor
    from .version import __version__


def load_commands_from_file(file_path):
    """安全加载 JSON 文件，尝试多种编码并在失败时给出友好提示。

    优先尝试 UTF-8/UTF-8-SIG，然后回退到系统编码（GBK）或 latin-1，最后使用替换策略读取。
    这样可以避免 Windows 下默认使用 GBK 导致无法解析 UTF-8 文件的情况。
    """
    encodings_to_try = ["utf-8", "utf-8-sig", "gbk", "latin-1"]
    for enc in encodings_to_try:
        try:
            with open(file_path, "r", encoding=enc) as file:
                CommonUtils.print_log_line(f"Loading JSON '{file_path}' with encoding: {enc}")
                return json.load(file)
        except UnicodeDecodeError:
            # 尝试下一个编码
            continue
        except json.JSONDecodeError:
            # 文件读取成功但 JSON 无效，抛出以便上层处理
            raise
        except Exception:
            # 其它异常也继续尝试
            continue

    # 最后尝试以二进制方式读取并用替换策略解码，这样至少可以避免因编码问题崩溃
    try:
        with open(file_path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        CommonUtils.print_log_line(f"Loaded JSON '{file_path}' by fallback decode (utf-8 replace).")
        return json.loads(text)
    except Exception as e:
        CommonUtils.print_log_line(f"❌ 无法加载 JSON 文件 '{file_path}': {e}")
        raise

def merge_config(config: json, dict_data: json):
    for key, value in config.items():
        if key not in dict_data:
            dict_data[key] = value
        elif isinstance(value, dict):
            merge_config(value, dict_data[key])

def apply_configs_for_device(configForDevice: json, dictForDevices: json):
    # Use Global Configurations for all devices
    for device in dictForDevices:
        if "status" not in device:
            device["status"] = configForDevice.get("status", "enabled")
        if "baud_rate" not in device:
            device["baud_rate"] = configForDevice.get("baud_rate", 115200)
        if "stop_bits" not in device:
            device["stop_bits"] = configForDevice.get("stop_bits", serial.STOPBITS_ONE)
        if "parity" not in device:
            device["parity"] = configForDevice.get("parity", serial.PARITY_NONE)
        if "data_bits" not in device:
            device["data_bits"] = configForDevice.get("data_bits", serial.EIGHTBITS)
        if "flow_control" not in device:
            device["flow_control"] = configForDevice.get("flow_control", None)
        if "dtr" not in device:
            device["dtr"] = configForDevice.get("dtr", False)
        if "rts" not in device:
            device["rts"] = configForDevice.get("rts", False)
        if "monitor" not in device:
            device["monitor"] = configForDevice.get("monitor", False)

def apply_configs_for_commands(configForCommands: json, dict: json):
    # Use Global Configurations cover all commands if not defined
    device_disabled = False
    for command in dict["Commands"]:
        # Get the device status from ConfigForDevices if it exists
        device_name = command.get("device")
        if device_name:
            for device in dict["Devices"]:
                if (
                    device["name"] == device_name
                    and device.get("status") == "disabled"
                ):
                    device_disabled = True
                    break

        # Set command status to disabled if device is disabled, otherwise use config default
        if device_disabled:
            command["status"] = "disabled"
            device_disabled = False
        elif "status" not in command:
            command["status"] = configForCommands.get("status", "enabled")

        if "device" not in command:
            command["device"] = configForCommands.get("device", None)
        if "order" not in command:
            command["order"] = configForCommands.get("order", 1)
        if "timeout" not in command:
            command["timeout"] = configForCommands.get("timeout", 3000)
        if "concurrent_strategy" not in command:
            command["concurrent_strategy"] = configForCommands.get(
                "concurrent_strategy", "sequential"
            )

        # Define action types to copy from config
        action_types = [
            "success_actions",
            "error_actions",
            "success_response_actions",
            "error_response_actions",
        ]
        for action_type in action_types:
            # Initialize with empty list if not exists
            if action_type not in command:
                command[action_type] = []

            # Append from config if exists
            if action_type in configForCommands:
                command[action_type].extend(configForCommands[action_type])

def execute_with_loop(dict_path: str, loop_count=3, infinite_loop=False, config=None):
    # Load the dictionary file
    dict_data = load_commands_from_file(dict_path)

    # Merge configuration if provided
    if config:
        merge_config(config, dict_data)
    
    try:
        if "ConfigForDevices" in dict_data:
            apply_configs_for_device(dict_data.get("ConfigForDevices", {}), dict_data.get("Devices", {}))

        # 创建 CommandExecutor，让它来创建 CommandDeviceDict
        executor = CommandExecutor(dict_data)
        command_device_dict = executor.command_device_dict
        
        # Save the DICT content to a file in the log_date_dir, for later reference
        dict_filename = os.path.basename(dict_path)  # Extract the file name from the path
        output_file_path = os.path.join(command_device_dict.log_date_dir, dict_filename)

        try:
            with open(output_file_path, "w") as output_file:
                json.dump(dict_data, output_file, indent=2)
            CommonUtils.print_log_line(f"Dictionary saved to {output_file_path}")
        except Exception as e:
            CommonUtils.print_log_line(f"Error saving dictionary to file: {e}")

        # Sort commands by ORDER but preserve original sequence for same order values
        commands = sorted(
            enumerate(command_device_dict.dict["Commands"]),
            key=lambda x: (
                x[1]["order"],
                x[0],
            ),  # Sort by order first, then by original index
        )
        commands = [cmd[1] for cmd in commands]  # Extract just the commands

        # If ConfigForCommands exists, apply configurations to commands
        if "ConfigForCommands" in command_device_dict.dict:
            apply_configs_for_commands(
                command_device_dict.dict.get("ConfigForCommands", {}), command_device_dict.dict
            )

        failure_count = 0
        executed_count = 0  # Track actual number of COMPLETED iterations
        
        # Use while True for infinite loop mode, otherwise use for loop
        if infinite_loop:
            CommonUtils.print_log_line(
                line="🔄 Infinite loop mode enabled - Press Ctrl+C to stop",
                top_border=True,
                bottom_border=True,
                side_border=True,
                border_side_char="*",
                border_vertical_char="*",
            )
            iteration = 0
            while True:
                iteration += 1
                current_iteration = executed_count + 1  # 显示当前正在执行的迭代编号
                CommonUtils.print_log_line(
                    line=f"💬 Executing iteration {current_iteration}",
                    top_border=True,
                    bottom_border=True,
                    side_border=True,
                    border_side_char="+",
                    border_vertical_char="+",
                )
                try:
                    result = executor.execute()
                    executed_count += 1  # 只有成功完成才增加计数
                except Exception as e:
                    # 获取设备信息用于错误提示
                    device_info = []
                    for dev_name, dev in command_device_dict.devices.items():
                        if hasattr(dev, 'port'):
                            device_info.append(f"{dev_name}({dev.port})")
                        else:
                            device_info.append(dev_name)
                    devices_str = ", ".join(device_info) if device_info else "Unknown"
                    
                    CommonUtils.print_log_line(f"❌ Error during iteration {current_iteration}: {e}")
                    CommonUtils.print_log_line(f"   Devices involved: {devices_str}")
                    executed_count += 1  # 即使失败也算完成了一次
                    result = False
                
                info = (
                    f"✅ Iteration {executed_count} passed."
                    if result
                    else f"❌ Iteration {executed_count} failed."
                )
                if not result:
                    failure_count += 1
                    info += f" (Total: {failure_count} {'iteration' if failure_count == 1 else 'iterations'} failed)"
                else:
                    info += f" (Total: {executed_count - failure_count} passed)"
                CommonUtils.print_log_line(
                    line=info,
                    top_border=True,
                    bottom_border=True,
                    side_border=True,
                    border_side_char="|",
                    border_vertical_char="-",
                )
        else:
            # Normal loop with specified count
            for i in range(loop_count):
                current_iteration = executed_count + 1  # 显示当前正在执行的迭代编号
                CommonUtils.print_log_line(
                    line=f"{'💬 Executing iteration ' + str(current_iteration) + '/' + str(loop_count)}",
                    top_border=True,
                    bottom_border=True,
                    side_border=True,
                    border_side_char="+",
                    border_vertical_char="+",
                )
                try:
                    result = executor.execute()
                    executed_count += 1  # 只有成功完成才增加计数
                except Exception as e:
                    # 获取设备信息用于错误提示
                    device_info = []
                    for dev_name, dev in command_device_dict.devices.items():
                        if hasattr(dev, 'port'):
                            device_info.append(f"{dev_name}({dev.port})")
                        else:
                            device_info.append(dev_name)
                    devices_str = ", ".join(device_info) if device_info else "Unknown"
                    
                    CommonUtils.print_log_line(f"❌ Error during iteration {current_iteration}: {e}")
                    CommonUtils.print_log_line(f"   Devices involved: {devices_str}")
                    executed_count += 1  # 即使失败也算完成了一次
                    result = False
                
                info = (
                    f"{'✅ ' + str(executed_count)}/{loop_count} iterations passed."
                    if result
                    else "❌ "
                    + str(executed_count)
                    + "/"
                    + str(loop_count)
                    + " iterations failed."
                )
                if not result:
                    failure_count += 1
                    info += f" ({failure_count}) {'iteration' if failure_count == 1 else 'iterations'} failed"
                CommonUtils.print_log_line(
                    line=info,
                    top_border=True,
                    bottom_border=True,
                    side_border=True,
                    border_side_char="|",
                    border_vertical_char="-",
                )

    except FileNotFoundError:
        CommonUtils.print_log_line(f"Error: Dictionary file '{dict_path}' not found")
        sys.exit(1)
    except json.JSONDecodeError:
        CommonUtils.print_log_line(f"Error: Invalid JSON format in '{dict_path}'")
        sys.exit(1)
    finally:
        # close all devices and save data
        if 'command_device_dict' in locals():
            command_device_dict.close_all_devices()  # Use the new method to properly cleanup
        if 'executor' in locals():
            executor.data_store.stop()
        
        # Use executed_count (actual iterations) instead of loop_count in summary
        if executed_count == 0:
            summary_line = "🧾 Summary: No iterations were executed."
        elif failure_count == 0:
            summary_line = f"🧾 Summary:{executed_count - failure_count}/{executed_count} iterations passed."
        else:
            summary_line = f"🧾 Summary:{failure_count}/{executed_count} iterations failed."
        CommonUtils.print_log_line(
            line=summary_line,
            top_border=True,
            bottom_border=True,
            side_border=True,
            border_side_char="|",
                border_vertical_char="-",
            )

def execute_with_folder(path: str, files: list, config: json = None):
    template_dict = {}
    if config:
        merge_config(config, template_dict)
    
    if "ConfigForDevices" in template_dict:
        apply_configs_for_device(template_dict.get("ConfigForDevices", {}), template_dict.get("Devices", {}))
        
    # 创建 CommandExecutor，让它来创建 CommandDeviceDict
    executor = CommandExecutor(template_dict)
    command_device_dict = executor.command_device_dict

    failure_count = 0
    try:
        for file in files:
            dict_path = os.path.join(path, file)
            dict_data = load_commands_from_file(dict_path)
            
            # Force merge `Commands` key from dictionary file to `command_device_dict`
            for key, value in dict_data.items():
                if key == "Commands":
                    command_device_dict.dict[key] = value
                    
            # Sort commands by order but preserve original sequence for same order values
            commands = sorted(
                enumerate(command_device_dict.dict["Commands"]),
                key=lambda x: (
                    x[1]["order"],
                    x[0],
                ),  # Sort by order first, then by original index
            )
            commands = [cmd[1] for cmd in commands]  # Extract just the commands

            if "ConfigForCommands" in command_device_dict.dict:
                apply_configs_for_commands(
                    command_device_dict.dict.get("ConfigForCommands", {}), command_device_dict.dict
                )
            executor = CommandExecutor(command_device_dict)

            CommonUtils.print_log_line(
                line=f"{'💬 Executing dictionary file ' + file}",
                top_border=True,
                bottom_border=True,
                side_border=True,
                border_side_char="+",
                border_vertical_char="+",
            )
                
            result = executor.execute()
            info = (
                f"{'✅ ' + file} passed."
                if result
                else "❌ "
                + file
                + " failed."
            )
            if not result:
                failure_count += 1
                info += f" ({failure_count}) {'file' if failure_count == 1 else 'files'} failed"
            CommonUtils.print_log_line(
                line=info,
                top_border=True,
                bottom_border=True,
                side_border=True,
            border_side_char="|",
            border_vertical_char="-",
        )
            # Wait 1 second between files
            # time.sleep(1)
    
    except FileNotFoundError:
        CommonUtils.print_log_line(f"Error: Dictionary file '{dict_path}' not found")
        sys.exit(1)
    except json.JSONDecodeError:
        CommonUtils.print_log_line(f"Error: Invalid JSON format in '{dict_path}'")
        sys.exit(1)
    finally:
        # close all devices and save data
        command_device_dict.close_all_devices()  # Use the new method to properly cleanup
        executor.data_store.force_save()  # Use force_save instead of non-existent save_to_file
        executor.data_store.stop()
        CommonUtils.print_log_line(
            f"{'✅ ' + str(len(files) - failure_count) + '/' + str(len(files))} files passed."
            if failure_count == 0
            else f"❌ {failure_count}/{len(files)} files failed.",
            top_border=True,
            bottom_border=True,
            side_border=True,
            border_side_char="|",
            border_vertical_char="-",
        )
        
def monitor_folder(folder_path, file_queue, stop_event):
    """
    Monitor a folder for new JSON files and add them to the execution queue.
    """
    CommonUtils.print_log_line(f"Starting to monitor folder: {folder_path}")
    
    # 用于跟踪已处理文件的字典，键为文件路径，值为(修改时间, 内容哈希)元组
    processed_files = {}

    # 确保文件夹存在
    if not os.path.exists(folder_path):
        CommonUtils.print_log_line(f"Folder '{folder_path}' does not exist. Creating it.")
        os.makedirs(folder_path)

    while not stop_event.is_set():
        try:
            # 获取文件夹中的所有 JSON 文件
            json_files = [
                f for f in os.listdir(folder_path) if f.endswith(".json")
            ]

            # 遍历文件，检查是否有新增或修改的文件
            for file_name in json_files:
                if stop_event.is_set():
                    break
                    
                file_path = os.path.join(folder_path, file_name)
                
                # 获取文件修改时间和大小
                mod_time = os.path.getmtime(file_path)
                file_size = os.path.getsize(file_path)
                
                # 计算文件内容的哈希值
                try:
                    with open(file_path, "rb") as f:
                        content = f.read()
                        content_hash = hash(content)
                except Exception:
                    # 如果无法读取文件，则跳过
                    continue
                
                # 检查文件是否为新文件或已被修改
                current_info = (mod_time, content_hash)
                if file_path not in processed_files or processed_files[file_path] != current_info:
                    CommonUtils.print_log_line(f"{'New' if file_path not in processed_files else 'Modified'} file detected: {file_name}")
                    try:
                        file_queue.put_nowait(file_path)  # 非阻塞添加
                        processed_files[file_path] = current_info  # 更新记录
                    except queue.Full:
                        CommonUtils.print_log_line(f"Queue is full, skipping file: {file_name}")

            # 每秒检查一次，但使用可中断的等待
            if not stop_event.wait(1.0):
                continue
            else:
                break

        except Exception as e:
            CommonUtils.print_log_line(f"Error in folder monitoring: {e}")
            if not stop_event.wait(1.0):
                continue
            else:
                break
    
    CommonUtils.print_log_line("Folder monitoring stopped")

def process_file_queue(file_queue, stop_event):
    """
    Continuously process files from the queue.
    """
    failure_count = 0
    total_files = 0

    while not stop_event.is_set():
        try:
            # 从队列中获取文件路径，使用超时避免无限阻塞
            try:
                file_path = file_queue.get(timeout=1.0)  # 1秒超时
            except queue.Empty:
                continue  # 队列为空，继续循环检查停止事件
                
            file_name = os.path.basename(file_path)
            total_files += 1

            command_device_dict = None
            executor = None
            
            try:
                # 加载 JSON 文件内容（使用统一的加载函数以处理编码问题）
                dict_data = load_commands_from_file(file_path)
                    
                if "ConfigForDevices" in dict_data:
                    apply_configs_for_device(dict_data.get("ConfigForDevices", {}), dict_data.get("Devices", {}))
                    
                command_device_dict = CommandDeviceDict(dict_data)
                
                # Save the dict content to a file in the log_date_dir
                dict_filename = os.path.basename(file_path)
                output_file_path = os.path.join(command_device_dict.log_date_dir, dict_filename)

                try:
                    with open(output_file_path, "w") as output_file:
                        json.dump(dict_data, output_file, indent=2)
                    CommonUtils.print_log_line(f"Dictionary saved to {output_file_path}")
                except Exception as e:
                    CommonUtils.print_log_line(f"Error saving dictionary to file: {e}")

                # Sort commands by order but preserve original sequence for same order values
                commands = sorted(
                    enumerate(command_device_dict.dict["Commands"]),
                    key=lambda x: (
                        x[1]["order"],
                        x[0],
                    ),
                )
                commands = [cmd[1] for cmd in commands]

                if "ConfigForCommands" in command_device_dict.dict:
                    apply_configs_for_commands(
                        command_device_dict.dict.get("ConfigForCommands", {}), command_device_dict.dict
                    )
                
                executor = CommandExecutor(command_device_dict)

                CommonUtils.print_log_line(
                    line=f"{'💬 Executing dictionary file ' + file_name}",
                    top_border=True,
                    bottom_border=True,
                    side_border=True,
                    border_side_char="+",
                    border_vertical_char="+",
                )

                result = executor.execute()
                info = (
                    f"{'✅ ' + file_name} passed."
                    if result
                    else "❌ "
                    + file_name
                    + " failed."
                )
                if not result:
                    failure_count += 1
                    info += f" ({failure_count}) {'file' if failure_count == 1 else 'files'} failed"
                CommonUtils.print_log_line(
                    line=info,
                    top_border=True,
                    bottom_border=True,
                    side_border=True,
                    border_side_char="|",
                    border_vertical_char="-",
                )

                # 删除文件
                os.remove(file_path)
                CommonUtils.print_log_line(f"File '{file_name}' executed and deleted.")

            except Exception as e:
                failure_count += 1
                CommonUtils.print_log_line(f"Error processing file '{file_name}': {e}")
            
            finally:
                # 确保正确清理资源
                if command_device_dict:
                    try:
                        command_device_dict.close_all_devices()
                    except Exception as e:
                        CommonUtils.print_log_line(f"Error closing devices: {e}")
                        
                if executor:
                    try:
                        executor.data_store.force_save()  # Use force_save instead of non-existent save_to_file
                        executor.data_store.stop()
                    except Exception as e:
                        CommonUtils.print_log_line(f"Error stopping executor: {e}")

            # 标记任务完成
            file_queue.task_done()

        except Exception as e:
            CommonUtils.print_log_line(f"Unexpected error in file processing: {e}")
            continue

    CommonUtils.print_log_line("File processing stopped")
    
    # 打印最终统计信息
    if total_files > 0:
        CommonUtils.print_log_line(
            f"{'✅ ' + str(total_files - failure_count) + '/' + str(total_files)} files processed."
            if failure_count == 0
            else f"❌ {failure_count}/{total_files} files failed.",
            top_border=True,
            bottom_border=True,
            side_border=True,
            border_side_char="|",
            border_vertical_char="-",
        )

def run_main():
    """主程序入口函数,用于被 CLI 调用"""
    # 获取当前工作目录（用户执行命令的目录）
    current_work_dir = os.getcwd()
    
    # 获取安装包目录（dicts/configs 等资源文件所在目录）
    package_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 在当前工作目录下创建 temps 和 device_logs
    temps_dir = os.path.join(current_work_dir, "temps")
    data_store_dir = os.path.join(temps_dir, "data_store")
    device_logs_dir = os.path.join(current_work_dir, "device_logs")
    
    # 确保目录存在
    os.makedirs(temps_dir, exist_ok=True)
    os.makedirs(data_store_dir, exist_ok=True)
    os.makedirs(device_logs_dir, exist_ok=True)
    
    # 设置全局日志目录（供 CommandDeviceDict 使用）
    os.environ['AUTOCOM_DEVICE_LOGS_DIR'] = device_logs_dir
    
    parser = argparse.ArgumentParser(
        description="AutoCom command execution tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  autocom -d dict.json -l 3              # 循环执行3次\n"
               "  autocom -d dict.json -i                # 无限循环\n"
               "  autocom -f dicts/                      # 文件夹模式\n"
               "  autocom -m temps/                      # 监控模式\n"
               "  autocom -d dict.json -c config.json    # 使用配置文件\n"
    )
    
    # 添加版本参数
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"AutoCom v{__version__}",
        help="Show version information and exit"
    )
    
    group1 = parser.add_mutually_exclusive_group()
    group1.add_argument(
        "-f",
        "--folder",
        type=str,
        help="Path to the folder containing dictionary JSON files (default: dicts)",
    )
    group1.add_argument(
        "-d",
        "--dict",
        type=str,
        help="Path to the dictionary JSON file (default: dicts/dict.json)",
    )

    parser.add_argument(
        "-l",
        "--loop",
        default=3,
        type=int,
        help="Number of times to loop execution (default: 3)",
    )
    parser.add_argument(
        "-i",
        "--infinite",
        action="store_true",
        help="Enable infinite loop mode - keep running until Ctrl+C is pressed",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Path to the configuration JSON file (default: config.json)",
    )
    parser.add_argument(
        "-m",
        "--monitor",
        type=str,
        help="Enable monitoring mode (you can also use -c/--config with this)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize current directory with AutoCom project structure (creates dicts, configs, temps folders with examples)",
    )

    # 检查是否没有提供任何参数
    if len(sys.argv) == 1:
        # 显示欢迎信息
        print()
        print(f"🚀 AutoCom v{__version__}")
        print("   串口自动化指令执行工具 - 支持多设备、多指令的串行和并行执行")
        print()
        print(f"📂 工作目录: {current_work_dir}")
        print(f"💾 数据存储目录: {data_store_dir}")
        print(f"📋 设备日志目录: {device_logs_dir}")
        print()
        print("🎯 初始化执行目录:")
        print("   autocom --init                      # 在当前目录创建执行结构和示例文件")
        print()
        print("📖 快速开始:")
        print("   autocom -d dict.json -l 3           # 执行字典文件，循环3次")
        print("   autocom -d dict.json -i             # 无限循环模式")
        print("   autocom -f dicts/                   # 执行文件夹内所有字典")
        print("   autocom -m temps/                   # 监控模式")
        print()
        print("🔍 更多帮助:")
        print("   autocom --help                      # 查看完整帮助")
        print("   autocom -v                          # 查看版本信息")
        print()
        print("📚 文档: https://github.com/iFishin/AutoCom")
        print()
        print()
        sys.exit(0)
    
    args = parser.parse_args()

    # 处理 --init 参数
    if args.init:
        CommonUtils.print_log_line("🚀 Initializing AutoCom project structure...", top_border=True)
        
        try:
            # 创建目录结构
            dirs_to_create = {
                "dicts": "Dictionary files (JSON)",
                "configs": "Configuration files (JSON)",
                "temps": "Temporary data storage",
                "device_logs": "Device execution logs"
            }
            
            for dir_name, description in dirs_to_create.items():
                dir_path = os.path.join(current_work_dir, dir_name)
                if os.path.exists(dir_path):
                    CommonUtils.print_log_line(f"   ⚠️  Directory '{dir_name}/' already exists - skipped")
                else:
                    os.makedirs(dir_path, exist_ok=True)
                    CommonUtils.print_log_line(f"   ✅ Created '{dir_name}/' - {description}")
            
            # 生成示例文件
            dest_dicts = os.path.join(current_work_dir, "dicts")
            dest_configs = os.path.join(current_work_dir, "configs")
            
            # 生成示例字典文件 - dict.json
            dict_example_path = os.path.join(dest_dicts, "dict.json")
            if not os.path.exists(dict_example_path):
                dict_example = {
                    "Devices": [
                        {
                            "name": "DeviceA",
                            "status": "enabled",
                            "port": "COM3",
                            "baud_rate": 115200,
                            "stop_bits": 1,
                            "parity": None,
                            "data_bits": 8,
                            "flow_control": None,
                            "dtr": False,
                            "rts": False
                        }
                    ],
                    "Commands": [
                        {
                            "name": "Echo Test",
                            "device": "DeviceA",
                            "order": 1,
                            "command": "AT\\r\\n",
                            "expected_response": "OK",
                            "timeout": 3000,
                            "status": "enabled"
                        },
                        {
                            "name": "Version Check",
                            "device": "DeviceA",
                            "order": 2,
                            "command": "AT+GMR\\r\\n",
                            "expected_response": "OK",
                            "timeout": 3000,
                            "status": "enabled"
                        }
                    ]
                }
                with open(dict_example_path, "w", encoding="utf-8") as f:
                    json.dump(dict_example, f, indent=2, ensure_ascii=False)
                CommonUtils.print_log_line(f"   📄 Created example: dicts/dict.json")
            else:
                CommonUtils.print_log_line(f"   ⚠️  dicts/dict.json already exists - skipped")
            
            # 生成示例配置文件
            config_example_path = os.path.join(dest_configs, "example.json")
            if not os.path.exists(config_example_path):
                config_example = {
                    "ConfigForDevices": {
                        "baud_rate": 115200,
                        "stop_bits": 1,
                        "parity": None,
                        "data_bits": 8
                    },
                    "ConfigForCommands": {
                        "timeout": 3000,
                        "status": "enabled"
                    }
                }
                with open(config_example_path, "w", encoding="utf-8") as f:
                    json.dump(config_example, f, indent=2, ensure_ascii=False)
                CommonUtils.print_log_line(f"   📄 Created example: configs/example.json")
            else:
                CommonUtils.print_log_line(f"   ⚠️  configs/example.json already exists - skipped")
            
            # 创建 README
            readme_path = os.path.join(current_work_dir, "README.md")
            if not os.path.exists(readme_path):
                readme_content = """# AutoCom Project

## Directory Structure

- `dicts/` - Dictionary files (command definitions)
- `configs/` - Configuration files
- `temps/` - Temporary data storage
- `device_logs/` - Device execution logs

## Quick Start

```bash
# Execute a dictionary file
autocom -d dicts/dict.json -l 3

# Execute with config
autocom -d dicts/dict.json -c configs/example.json -l 5

# Monitor mode
autocom -m temps/
```

## Documentation

Visit: https://github.com/iFishin/AutoCom
"""
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(readme_content)
                CommonUtils.print_log_line(f"   📝 Created README.md")
            else:
                CommonUtils.print_log_line(f"   ⚠️  README.md already exists - skipped")
            
            CommonUtils.print_log_line(
                "✨ Initialization complete! You can now use AutoCom in this directory.",
                bottom_border=True,
                side_border=True,
                border_side_char="="
            )
            CommonUtils.print_log_line("💡 Tip: Edit files in dicts/ to customize your commands")
            CommonUtils.print_log_line("💡 Tip: Run 'autocom -d dicts/dict.json -l 3' to test")
            
        except Exception as e:
            CommonUtils.print_log_line(f"❌ Error during initialization: {e}", bottom_border=True)
            sys.exit(1)
        
        sys.exit(0)

    # 初始化 config 变量（防止未定义错误）
    config = None
    config_path = None

    if args.config:
        # 配置文件相对于安装包目录
        if os.path.isabs(args.config):
            config_path = args.config
        else:
            config_path = os.path.join(package_dir, "configs", args.config)
        
        try:
            with open(config_path, "r") as file:
                config = json.load(file)
        except FileNotFoundError:
            CommonUtils.print_log_line(f"Error: Config file '{config_path}' not found")
            sys.exit(1)
        except json.JSONDecodeError:
            CommonUtils.print_log_line(f"Error: Invalid JSON format in '{config_path}'")
            sys.exit(1)

    if args.dict:
        # 处理字典文件路径
        if os.path.isabs(args.dict):
            # 绝对路径直接使用
            dict_path = args.dict
        else:
            # 相对路径:优先从当前工作目录查找,如果不存在则从包目录查找
            current_dict_path = os.path.join(current_work_dir, args.dict)
            package_dict_path = os.path.join(package_dir, "dicts", args.dict)
            
            if os.path.exists(current_dict_path):
                dict_path = current_dict_path
            elif os.path.exists(package_dict_path):
                dict_path = package_dict_path
            else:
                # 都不存在,使用当前目录的路径(让后续错误处理显示正确的路径)
                dict_path = current_dict_path

        start_time = time.time()
        try:
            execute_with_loop(dict_path, args.loop, args.infinite, config)
        except KeyboardInterrupt:
            CommonUtils.print_log_line("Execution interrupted by user")
        except FileNotFoundError as e:
            CommonUtils.print_log_line(f"Error: Dictionary file not found: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            CommonUtils.print_log_line(f"Error: Invalid JSON format: {e}")
            sys.exit(1)
        finally:
            end_time = time.time()
            execution_time = end_time - start_time
            hours = int(execution_time // 3600)
            minutes = int((execution_time % 3600) // 60)
            seconds = execution_time % 60
            CommonUtils.print_log_line(
                f"Total execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f}",
                top_border=True,
                bottom_border=True,
            )
    elif args.folder:
        # 文件夹路径相对于安装包目录
        if os.path.isabs(args.folder):
            folder_path = args.folder
        else:
            folder_path = os.path.join(package_dir, "dicts", args.folder)
        
        json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
        sorted_files = sorted(
            json_files,
            key=lambda x: (
                int(re.match(r"(\d+)", x).group(1))
                if re.match(r"(\d+)", x)
                else float("inf")
            ),
        )
        
        try:
            start_time = time.time()
            execute_with_folder(folder_path, sorted_files, config)
        except KeyboardInterrupt:
            CommonUtils.print_log_line("Execution interrupted by user")
        except FileNotFoundError as e:
            CommonUtils.print_log_line(f"Error: Folder or file not found: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            CommonUtils.print_log_line(f"Error: Invalid JSON format: {e}")
            sys.exit(1)
        finally:
            end_time = time.time()
            execution_time = end_time - start_time
            hours = int(execution_time // 3600)
            minutes = int((execution_time % 3600) // 60)
            seconds = execution_time % 60
            CommonUtils.print_log_line(
                f"Total execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f}",
                top_border=True,
                bottom_border=True,
            )
    elif args.monitor:
        folder_to_monitor = "temps"
        if args.folder:
            folder_to_monitor = args.folder  # 如果指定了文件夹，则使用指定的路径

        CommonUtils.print_log_line(
            line=f"Monitoring mode enabled. Monitoring folder: {folder_to_monitor}",
            top_border=True,
            bottom_border=True,
            side_border=True,
            border_side_char="+",
            border_vertical_char="+"
        )

        # 初始化文件队列
        file_queue = queue.Queue(maxsize=64)  # 设置队列大小为64
        
        # 用于控制线程停止的事件
        stop_event = threading.Event()

        # 启动监控线程
        monitor_thread = threading.Thread(
            target=monitor_folder, args=(folder_to_monitor, file_queue, stop_event), daemon=True
        )
        monitor_thread.start()

        # 启动文件处理线程
        process_thread = threading.Thread(
            target=process_file_queue, args=(file_queue, stop_event), daemon=True
        )
        process_thread.start()

        # 主线程保持运行，但响应中断信号
        try:
            CommonUtils.print_log_line("Monitoring started. Press Ctrl+C to stop.")
            while not stop_event.is_set():
                time.sleep(0.1)  # 更短的睡眠时间，更快响应
        except KeyboardInterrupt:
            CommonUtils.print_log_line("Monitoring interrupted by user.")
            stop_event.set()  # 通知所有线程停止
            
            # 等待线程结束
            monitor_thread.join(timeout=2)
            process_thread.join(timeout=2)
            
            CommonUtils.print_log_line("All monitoring threads stopped.")
            sys.exit(0)

if __name__ == "__main__":
    run_main()
