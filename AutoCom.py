import serial
import time
import json
import threading
import os
import re
import queue
import sys
from utils.common import CommonUtils
from components.CommandDeviceDict import CommandDeviceDict
from components.CommandExecutor import CommandExecutor
from version import __version__
from components.Logger import AutoComLogger, get_logger

logger: AutoComLogger = get_logger(name="AutoCom")


def load_commands_from_file(file_path):
    """Safely load a JSON file, attempting multiple encodings and providing friendly error messages on failure.

    Prioritize UTF-8/UTF-8-SIG, then fallback to system encoding (GBK) or latin-1, and finally use a replacement strategy for reading.
    This helps avoid issues where the default GBK encoding on Windows prevents parsing of UTF-8 files.
    """
    encodings_to_try = ["utf-8", "utf-8-sig", "gbk", "latin-1"]
    for enc in encodings_to_try:
        try:
            with open(file_path, "r", encoding=enc) as file:
                logger.log_session_start(
                    f"Loading JSON file '{file_path}' using encoding: {enc}"
                )
                return json.load(file)
        except UnicodeDecodeError:
            # Try next encoding
            continue
        except json.JSONDecodeError:
            # File read succeeded but JSON is invalid — re-raise for upper layer to handle
            raise
        except Exception:
            # Other errors, try next encoding
            continue

    # Final attempt: read as binary and decode with replacement to avoid crashing on encoding issues
    try:
        with open(file_path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        logger.log_session_start(
            f"Loaded JSON file '{file_path}' using fallback decoding (utf-8 with replace)."
        )
        return json.loads(text)
    except Exception as e:
        logger.log_session_error(f"❌ Failed to load JSON file '{file_path}': {e}")
        raise


def merge_config(config: dict, dict_data: dict):
    for key, value in config.items():
        if key not in dict_data:
            dict_data[key] = value
        elif isinstance(value, dict):
            merge_config(value, dict_data[key])


def ensure_working_directories(temps_dir, data_store_dir, device_logs_dir):
    """Ensure all working directories exist

    Args:
        temps_dir: Path to temporary directory (can be str or Path)
        data_store_dir: Path to data store directory (can be str or Path)
        device_logs_dir: Path to device logs directory (can be str or Path)
    """
    from pathlib import Path

    Path(temps_dir).mkdir(parents=True, exist_ok=True)
    Path(data_store_dir).mkdir(parents=True, exist_ok=True)
    Path(device_logs_dir).mkdir(parents=True, exist_ok=True)


def apply_configs_for_device(configForDevice: dict, dictForDevices: dict):
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


def apply_configs_for_commands(configForCommands: dict, dict: dict):
    # Use Global Configurations cover all commands if not defined
    device_disabled = False
    for command in dict["Commands"]:
        # Get the device status from ConfigForDevices if it exists
        device_name = command.get("device")
        if device_name:
            for device in dict["Devices"]:
                if device["name"] == device_name and device.get("status") == "disabled":
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

    # Initialize counters before try block to avoid UnboundLocalError in finally
    executed_count = 0
    failure_count = 0
    command_device_dict = None
    executor = None

    try:
        if "ConfigForDevices" in dict_data:
            apply_configs_for_device(
                dict_data.get("ConfigForDevices", {}), dict_data.get("Devices", {})
            )

        # Create CommandExecutor to create CommandDeviceDict
        executor = CommandExecutor(dict_data)
        command_device_dict = executor.command_device_dict

        # Save the DICT content to a file in the log_date_dir, for later reference
        from pathlib import Path

        dict_filename = Path(dict_path).name  # Extract the file name from the path
        output_file_path = Path(command_device_dict.log_date_dir) / dict_filename

        try:
            with open(output_file_path, "w") as output_file:
                json.dump(dict_data, output_file, indent=2)
            logger.log_session_start(f"Dictionary saved to {output_file_path}")
        except Exception as e:
            logger.log_session_error(f"Error saving dictionary to file: {e}")

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
                command_device_dict.dict.get("ConfigForCommands", {}),
                command_device_dict.dict,
            )

        failure_count = 0
        executed_count = 0  # Track actual number of COMPLETED iterations

        # Use while True for infinite loop mode, otherwise use for loop
        if infinite_loop:
            logger.log_session_start(
                "🔄 Infinite loop mode enabled - Press Ctrl+C to stop"
            )
            iteration = 0
            while True:
                iteration += 1
                current_iteration = executed_count + 1  # 显示当前正在执行的迭代编号
                # logger.log_iteration_start(iteration=current_iteration, total=iteration)
                result = False  # Initialize result before try block
                try:
                    # Set iteration info in executor for logging
                    executor.set_iteration_info(current_iteration)
                    result = executor.execute()
                    executed_count += 1
                except Exception as e:
                    # 获取设备信息用于错误提示
                    device_info = []
                    for dev_name, dev in command_device_dict.devices.items():
                        if hasattr(dev, "port"):
                            device_info.append(f"{dev_name}({dev.port})")
                        else:
                            device_info.append(dev_name)
                    devices_str = ", ".join(device_info) if device_info else "Unknown"

                    logger.log_iteration_error(
                        f"❌ Error during iteration {current_iteration}: {e}"
                    )
                    logger.log_iteration_error(f"Devices involved: {devices_str}")
                    executed_count += 1  # 即使失败也算完成了一次
                    result = False
        else:
            # Normal loop with specified count
            iteration = 0
            for i in range(loop_count):
                iteration += 1
                # logger.log_iteration_start(iteration=iteration, total=loop_count)
                current_iteration = executed_count + 1  # 显示当前正在执行的迭代编号
                result = False  # Initialize result before try block
                try:
                    # Set iteration info in executor for logging
                    executor.set_iteration_info(current_iteration, loop_count)
                    result = executor.execute()
                    executed_count += 1  # 只有成功完成才增加计数
                except Exception as e:
                    # 获取设备信息用于错误提示
                    device_info = []
                    for dev_name, dev in command_device_dict.devices.items():
                        if hasattr(dev, "port"):
                            device_info.append(f"{dev_name}({dev.port})")
                        else:
                            device_info.append(dev_name)
                    devices_str = ", ".join(device_info) if device_info else "Unknown"

                    logger.log_iteration_error(
                        f"Error during iteration {current_iteration}: {e}"
                    )
                    logger.log_iteration_error(f"Devices involved: {devices_str}")
                    executed_count += 1  # 即使失败也算完成了一次
                    result = False
                if not result:
                    failure_count += 1
                logger.log_iteration_end(iteration=current_iteration, total=loop_count)
    except KeyboardInterrupt:
        logger.log_iteration_error("Execution interrupted by user")
        sys.exit(1)
    except FileNotFoundError:
        logger.log_iteration_error(f"Error: Dictionary file '{dict_path}' not found")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.log_iteration_error(f"Error: Invalid JSON format in '{dict_path}'")
        sys.exit(1)
    except (RuntimeError, Exception) as e:
        logger.log_iteration_error(f"Fatal: {e}")
        sys.exit(1)
    finally:
        # close all devices and save data
        if "command_device_dict" in locals() and command_device_dict is not None:
            command_device_dict.close_all_devices()
        if "executor" in locals() and executor is not None:
            try:
                # 关闭后台执行线程
                executor.shutdown()
            except Exception as e:
                logger.log_session_error(f"Warning: Error shutting down executor: {e}")

            try:
                executor.data_store.stop()
            except Exception as e:
                logger.log_session_error(f"Warning: Error stopping data store: {e}")

        # Use executed_count (actual iterations) instead of loop_count in summary
        if executed_count == 0:
            summary_line = "🧾 Summary: No iterations were executed."
        elif failure_count == 0:
            summary_line = f"🧾 Summary:{executed_count - failure_count}/{executed_count} iterations passed."
        else:
            summary_line = (
                f"🧾 Summary:{failure_count}/{executed_count} iterations failed."
            )
        logger.log_session_end(summary_line)


def execute_with_folder(path: str, files: list, config: dict = {}):
    template_dict = {}
    if config:
        merge_config(config, template_dict)

    if "ConfigForDevices" in template_dict:
        apply_configs_for_device(
            template_dict.get("ConfigForDevices", {}), template_dict.get("Devices", {})
        )

    # 创建 CommandDeviceDict 对象
    command_device_dict = CommandDeviceDict(template_dict)
    executor = CommandExecutor(command_device_dict)

    failure_count = 0
    dict_path = ""  # Initialize dict_path before try block
    try:
        from pathlib import Path

        for file in files:
            dict_path = str(Path(path) / file)
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
                    command_device_dict.dict.get("ConfigForCommands", {}),
                    command_device_dict.dict,
                )
            executor = CommandExecutor(command_device_dict)

            logger.log_session_start(f"{'💬 Executing dictionary file ' + file}")

            result = executor.execute()
            info = f"{'✅ ' + file} passed." if result else "❌ " + file + " failed."
            if not result:
                failure_count += 1
                info += f" ({failure_count}) {'file' if failure_count == 1 else 'files'} failed"
            logger.log_session_start(
                info,
            )
            # Wait 1 second between files
            # time.sleep(1)

    except FileNotFoundError:
        logger.log_session_error(f"Error: Dictionary file '{dict_path}' not found")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.log_session_error(f"Error: Invalid JSON format in '{dict_path}'")
        sys.exit(1)
    finally:
        # close all devices and save data
        command_device_dict.close_all_devices()  # Use the new method to properly cleanup
        try:
            executor.shutdown()
        except Exception as e:
            logger.log_session_error(f"Warning: Error shutting down executor: {e}")

        try:
            executor.data_store.force_save()  # Use force_save instead of non-existent save_to_file
            executor.data_store.stop()
        except Exception as e:
            logger.log_session_error(f"Warning: Error stopping data store: {e}")

        logger.log_session_end(
            (
                f"{'✅ ' + str(len(files) - failure_count) + '/' + str(len(files))} files passed."
                if failure_count == 0
                else f"❌ {failure_count}/{len(files)} files failed."
            )
        )


def monitor_folder(folder_path, file_queue, stop_event):
    """
    Monitor a folder for new JSON files and add them to the execution queue.
    """
    logger.log_session_info(f"Starting to monitor folder: {folder_path}")

    # 用于跟踪已处理文件的字典，键为文件路径，值为(修改时间, 内容哈希)元组
    processed_files = {}

    # 确保文件夹存在
    if not os.path.exists(folder_path):
        logger.log_session_info(f"Folder '{folder_path}' does not exist. Creating it.")
        os.makedirs(folder_path)

    while not stop_event.is_set():
        try:
            # 获取文件夹中的所有 JSON 文件
            json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]

            # 遍历文件，检查是否有新增或修改的文件
            from pathlib import Path

            for file_name in json_files:
                if stop_event.is_set():
                    break

                file_path = Path(folder_path) / file_name

                # 获取文件修改时间和大小
                mod_time = file_path.stat().st_mtime
                file_size = file_path.stat().st_size

                # 计算文件内容的哈希值
                try:
                    content = file_path.read_bytes()
                    content_hash = hash(content)
                except Exception:
                    # 如果无法读取文件，则跳过
                    continue

                # 检查文件是否为新文件或已被修改
                current_info = (mod_time, content_hash)
                if (
                    file_path not in processed_files
                    or processed_files[file_path] != current_info
                ):
                    logger.log_session_info(
                        f"{'New' if file_path not in processed_files else 'Modified'} file detected: {file_name}"
                    )
                    try:
                        file_queue.put_nowait(file_path)  # 非阻塞添加
                        processed_files[file_path] = current_info  # 更新记录
                    except queue.Full:
                        logger.log_session_error(
                            f"Queue is full, skipping file: {file_name}"
                        )

            # 每秒检查一次，但使用可中断的等待
            if not stop_event.wait(1.0):
                continue
            else:
                break

        except Exception as e:
            logger.log_session_error(f"Error in folder monitoring: {e}")
            if not stop_event.wait(1.0):
                continue
            else:
                break

    logger.log_session_end("Folder monitoring stopped")


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
                    apply_configs_for_device(
                        dict_data.get("ConfigForDevices", {}),
                        dict_data.get("Devices", {}),
                    )

                command_device_dict = CommandDeviceDict(dict_data)

                # Save the dict content to a file in the log_date_dir
                from pathlib import Path

                dict_filename = Path(file_path).name
                output_file_path = (
                    Path(command_device_dict.log_date_dir) / dict_filename
                )

                try:
                    with open(output_file_path, "w") as output_file:
                        json.dump(dict_data, output_file, indent=2)
                    logger.log_session_start(f"Dictionary saved to {output_file_path}")
                except Exception as e:
                    logger.log_session_error(f"Error saving dictionary to file: {e}")

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
                        command_device_dict.dict.get("ConfigForCommands", {}),
                        command_device_dict.dict,
                    )

                executor = CommandExecutor(command_device_dict)

                logger.log_session_start(
                    f"{'💬 Executing dictionary file ' + file_name}"
                )

                result = executor.execute()
                info = (
                    f"{'✅ ' + file_name} passed."
                    if result
                    else "❌ " + file_name + " failed."
                )
                if not result:
                    failure_count += 1
                    info += f" ({failure_count}) {'file' if failure_count == 1 else 'files'} failed"
                logger.log_session_info(info)

                # 删除文件
                os.remove(file_path)
                logger.log_session_info(f"File '{file_name}' executed and deleted.")

            except Exception as e:
                failure_count += 1
                logger.log_session_error(f"Error processing file '{file_name}': {e}")

            finally:
                # 确保正确清理资源
                if command_device_dict:
                    try:
                        command_device_dict.close_all_devices()
                    except Exception as e:
                        logger.log_session_error(f"Error closing devices: {e}")

                if executor:
                    try:
                        # 关闭后台执行线程
                        executor.shutdown()
                    except Exception as e:
                        logger.log_session_error(f"Error shutting down executor: {e}")

                    try:
                        executor.data_store.force_save()  # Use force_save instead of non-existent save_to_file
                        executor.data_store.stop()
                    except Exception as e:
                        logger.log_session_error(f"Error stopping executor: {e}")

            # 标记任务完成
            file_queue.task_done()

        except Exception as e:
            logger.log_session_error(f"Unexpected error in file processing: {e}")
            continue

    logger.log_session_end("File processing stopped")

    # 打印最终统计信息
    if total_files > 0:
        logger.log_session_end(
            (
                f"{'✅ ' + str(total_files - failure_count) + '/' + str(total_files)} files processed."
                if failure_count == 0
                else f"❌ {failure_count}/{total_files} files failed."
            )
        )
