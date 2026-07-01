import serial
import time
import json
import threading
import os
import re
import queue
import sys
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from utils.common import CommonUtils
from components.CommandDeviceDict import CommandDeviceDict
from components.CommandExecutor import CommandExecutor
from typing import Optional, Any
from version import __version__
from components.Logger import AutoComLogger, get_logger

logger: AutoComLogger = get_logger(name="AutoCom")


def load_commands_from_file(file_path):
    """Safely load a configuration file (JSON or YAML), attempting multiple encodings and providing friendly error messages on failure.

    The file format is automatically detected based on file extension:
    - .json -> JSON format
    - .yaml, .yml -> YAML format (requires PyYAML)

    Prioritize UTF-8/UTF-8-SIG, then fallback to system encoding (GBK) or latin-1, and finally use a replacement strategy for reading.
    This helps avoid issues where the default GBK encoding on Windows prevents parsing of UTF-8 files.
    """
    # Determine file format based on extension
    file_path_obj = Path(file_path)
    file_ext = file_path_obj.suffix.lower()

    if file_ext == ".json":
        loader = json.load
        format_name = "JSON"
        parser_error = json.JSONDecodeError
    elif file_ext in (".yaml", ".yml"):
        loader = yaml.safe_load
        format_name = "YAML"
        parser_error = yaml.YAMLError
    else:
        logger.log_session_error(
            f"❌ Unsupported file format: '{file_ext}'. Only .json, .yaml, and .yml files are supported."
        )
        raise ValueError(f"Unsupported file format: {file_ext}")

    encodings_to_try = ["utf-8", "utf-8-sig", "gbk", "latin-1"]
    for enc in encodings_to_try:
        try:
            with open(file_path, "r", encoding=enc) as file:
                logger.log_session_start(
                    f"Loading {format_name} file '{file_path}' using encoding: {enc}"
                )
                data = loader(file)
                # Validate that the loaded data is a dictionary
                if not isinstance(data, dict):
                    raise ValueError(
                        f"{format_name} file must contain a dictionary/object"
                    )
                return data
        except UnicodeDecodeError:
            # Try next encoding
            continue
        except parser_error:
            # File read succeeded but format is invalid — re-raise for upper layer to handle
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
            f"Loaded {format_name} file '{file_path}' using fallback decoding (utf-8 with replace)."
        )
        # Re-load with proper method based on format
        if format_name == "JSON":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)

        if not isinstance(data, dict):
            raise ValueError(f"{format_name} file must contain a dictionary/object")
        return data
    except Exception as e:
        logger.log_session_error(
            f"❌ Failed to load {format_name} file '{file_path}': {e}"
        )
        raise


def merge_config(config: dict, dict_data: dict):
    for key, value in config.items():
        # If key does not exist in target, copy it over
        if key not in dict_data:
            dict_data[key] = value
        else:
            # If both sides are dicts, merge recursively
            if isinstance(value, dict) and isinstance(dict_data.get(key), dict):
                merge_config(value, dict_data[key])
            else:
                # Otherwise prefer the value from `config` (overwrite)
                dict_data[key] = value


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


def apply_configs_for_device(configForDevice: dict, devices: list):
    """Apply global device-level defaults to each device dict in `devices`.

    Args:
        configForDevice: dict of default device settings
        devices: list of device dicts (as found under "Devices")
    """
    if not isinstance(devices, list):
        return

    for device in devices:
        if not isinstance(device, dict):
            continue

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


def apply_configs_for_commands(configForCommands: dict, dict_data: dict):
    """Apply global command defaults from `configForCommands` into `dict_data`.

    Args:
        configForCommands: dict of default command settings
        dict_data: dictionary that should contain a "Commands" list and optionally "Devices"
    """
    commands = dict_data.get("Commands", [])
    devices = dict_data.get("Devices", [])

    for command in commands:
        if not isinstance(command, dict):
            continue

        # Determine if the device for this command is disabled
        device_disabled = False
        device_name = command.get("device")
        if device_name and isinstance(devices, list):
            for device in devices:
                if (
                    isinstance(device, dict)
                    and device.get("name") == device_name
                    and device.get("status") == "disabled"
                ):
                    device_disabled = True
                    break

        # Apply status
        if device_disabled:
            command["status"] = "disabled"
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
            if action_type not in command or not isinstance(command[action_type], list):
                command[action_type] = []

            # Append from config if exists and is a list
            cfg_actions = configForCommands.get(action_type)
            if isinstance(cfg_actions, list):
                command[action_type].extend(cfg_actions)


# ── 配置文件保存（保留原始格式） ──

def _save_dict(dict_data: dict, output_path: str | Path):
    """将 dict_data 写入文件，根据 output_path 后缀自动选择格式。"""
    ext = Path(output_path).suffix.lower()
    if ext in (".yaml", ".yml"):
        import yaml
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(dict_data, f, allow_unicode=True, default_flow_style=False)
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dict_data, f, indent=2, ensure_ascii=False)


# ── 执行配置（从 Config 块读取 + CLI 覆盖） ──

@dataclass
class ExecutionConfig:
    """解析后的执行配置。CLI 参数优先于 Config 块。"""
    mode: str = "single"             # single | loop | infinite
    iterations: int = 1              # loop 模式的循环次数
    interval_ms: int = 0             # 迭代间隔（毫秒）
    max_duration_seconds: float = 0  # 最大执行时长（0=不限）
    stop_on_failure: bool = True     # 失败是否终止
    max_failures: int = 0            # 最大允许失败次数（0=不限）
    description: str = ""            # 配置文件描述


def _as_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_duration(text: str | None) -> float:
    """解析时长字符串为秒数。
    支持格式: 30(纯数字=秒), 30s(秒), 5m(分), 1h(时)
    返回 0 表示不限时。
    """
    if not text:
        return 0.0
    text = str(text).strip()
    if not text:
        return 0.0
    try:
        if text.endswith("h"):
            return float(text[:-1]) * 3600
        elif text.endswith("m"):
            return float(text[:-1]) * 60
        elif text.endswith("s"):
            return float(text[:-1])
        else:
            return float(text)
    except (ValueError, TypeError):
        logger.log_session_error(
            f"无法解析时长参数 '{text}'，支持格式: 30, 30s, 5m, 1h"
        )
        return 0.0


def resolve_execution_config(
    dict_data: dict,
    cli_loop: int | None = None,
    cli_infinite: bool = False,
    cli_mode: str | None = None,
    cli_duration: str | None = None,
) -> ExecutionConfig:
    """从配置文件的 Config 块 + CLI 参数合并执行配置。

    优先级：CLI 参数 > Config 块 > 兼容默认值
    """
    cfg = dict_data.get("Config", {}) or {}
    has_config = "Config" in dict_data

    # 顶层 loop 快捷写法: loop: 3  →  Config: {mode: loop, loop: {iterations: 3}}
    top_level_loop = dict_data.get("loop")
    if top_level_loop and isinstance(top_level_loop, (int, str)):
        has_config = True
        if cfg is None:
            cfg = {}
        cfg["mode"] = "loop"
        if isinstance(cfg.get("loop"), dict):
            cfg["loop"]["iterations"] = int(top_level_loop)
        else:
            cfg["loop"] = {"iterations": int(top_level_loop)}

    if has_config:
        # ── 新格式：配置文件声明执行方式 ──
        mode = cli_mode or cfg.get("mode", "single")
        if cli_loop is not None:
            mode = "loop"
        if cli_infinite:
            mode = "infinite"
        loop_cfg = cfg.get("loop", {}) or {}
        iterations = (
            cli_loop if cli_loop is not None
            else _as_int(loop_cfg.get("iterations", 1), 1)
        )
        if mode == "single":
            iterations = 1
        # duration：CLI 优先，其次 Config 块
        duration_raw = cli_duration if cli_duration is not None else loop_cfg.get("duration", "")
        max_duration = _parse_duration(duration_raw)
        return ExecutionConfig(
            mode=mode,
            iterations=_as_int(iterations, 1),
            interval_ms=_as_int(loop_cfg.get("interval_ms", 0), 0),
            max_duration_seconds=max_duration,
            stop_on_failure=(
                loop_cfg.get("stop_on_failure", False)
                if not cli_infinite else False
            ),
            max_failures=_as_int(loop_cfg.get("max_failures", 0), 0),
            description=cfg.get("description", ""),
        )
    else:
        # ── 旧格式：向后兼容，由 CLI 参数决定 ──
        mode = "infinite" if cli_infinite else "loop"
        iterations = cli_loop if cli_loop is not None else 3
        max_duration = _parse_duration(cli_duration)
        return ExecutionConfig(
            mode=mode, iterations=iterations,
            interval_ms=0, stop_on_failure=False, max_failures=0,
            max_duration_seconds=max_duration,
        )


def execute_with_loop(dict_path: str, loop_count: int | None = None, infinite_loop=False, config=None, duration: str | None = None):
    # Load the dictionary file
    dict_data = load_commands_from_file(dict_path)

    # Merge configuration if provided
    if config:
        merge_config(config, dict_data)

    # 解析执行配置
    exec_cfg = resolve_execution_config(
        dict_data, cli_loop=loop_count, cli_infinite=infinite_loop, cli_duration=duration,
    )

    logger.log_session_start(
        f"🚀 执行模式: {exec_cfg.mode}"
        + (f" × {exec_cfg.iterations}" if exec_cfg.mode == "loop" else "")
        + (f" — {exec_cfg.description}" if exec_cfg.description else "")
        + (f" ⏱ {duration}" if duration else "")
    )

    # Initialize counters before try block to avoid UnboundLocalError in finally
    executed_count = 0
    failure_count = 0
    command_device_dict: Optional[CommandDeviceDict] = None
    executor: Optional[CommandExecutor] = None

    try:
        # 始终执行设备默认值填充（即使没有 ConfigForDevices 块）
        apply_configs_for_device(
            dict_data.get("ConfigForDevices", {}), dict_data.get("Devices", [])
        )

        # Create CommandExecutor to create CommandDeviceDict
        executor = CommandExecutor(dict_data)
        command_device_dict = executor.command_device_dict

        # Save the DICT content to a file in the log_date_dir, for later reference
        from pathlib import Path

        dict_filename = Path(dict_path).name  # Extract the file name from the path
        if command_device_dict is not None and hasattr(
            command_device_dict, "log_date_dir"
        ):
            output_file_path = Path(command_device_dict.log_date_dir) / dict_filename
        else:
            output_file_path = None

        if output_file_path is not None:
            try:
                _save_dict(dict_data, output_file_path)
                logger.log_session_start(f"Dictionary saved to {output_file_path}")
            except Exception as e:
                logger.log_session_error(f"Error saving dictionary to file: {e}")

        # ── 兼容旧 Commands 格式：排序和应用全局配置 ──
        cdd_dict: Any = (
            command_device_dict.dict
            if command_device_dict is not None and hasattr(command_device_dict, "dict")
            else command_device_dict
        )
        if "Commands" in cdd_dict:
            commands = sorted(
                enumerate(cdd_dict["Commands"]),
                key=lambda x: (x[1]["order"], x[0]),
            )
            if "ConfigForCommands" in cdd_dict:
                apply_configs_for_commands(
                    cdd_dict.get("ConfigForCommands", {}),
                    cdd_dict,
                )

        # ── 统一执行循环 ──
        failure_count = 0
        executed_count = 0
        iteration = 0
        start_time = time.time()

        while True:
            iteration += 1

            # 终止条件：轮数上限
            if exec_cfg.mode == "single" and iteration > 1:
                break
            if exec_cfg.mode == "loop" and iteration > exec_cfg.iterations:
                break
            # 终止条件：时长上限
            if (
                exec_cfg.max_duration_seconds > 0
                and (time.time() - start_time) >= exec_cfg.max_duration_seconds
            ):
                logger.log_session_info("⏹️ 达到目标执行时长，自动停止")
                break

            current_iteration = executed_count + 1
            total_iterations = (
                exec_cfg.iterations
                if exec_cfg.mode == "loop"
                else 1 if exec_cfg.mode == "single"
                else None
            )

            if exec_cfg.mode == "infinite":
                logger.log_session_start(
                    f"🔄 迭代 #{current_iteration} — 无限模式 (Ctrl+C 停止)"
                )

            result = False
            try:
                executor.set_iteration_info(current_iteration, total_iterations)
                result = executor.execute()
                executed_count += 1
            except Exception as e:
                device_info = []
                if command_device_dict is not None and hasattr(
                    command_device_dict, "devices"
                ):
                    for dev_name, dev in command_device_dict.devices.items():
                        port = getattr(dev, "port", None)
                        device_info.append(
                            f"{dev_name}({port})" if port else dev_name
                        )
                devices_str = ", ".join(device_info) if device_info else "Unknown"
                logger.log_iteration_error(
                    f"❌ 迭代 #{current_iteration} 异常: {e}"
                )
                logger.log_iteration_error(f"涉及设备: {devices_str}")
                executed_count += 1

            if not result:
                failure_count += 1

            # 失败终止条件
            if not result and exec_cfg.stop_on_failure:
                logger.log_session_info(
                    "⏹️ 失败终止（stop_on_failure=true）"
                )
                break
            if (
                exec_cfg.max_failures > 0
                and failure_count >= exec_cfg.max_failures
            ):
                logger.log_session_info(
                    f"⏹️ 达到最大失败次数 {exec_cfg.max_failures}"
                )
                break

            logger.log_iteration_end(
                iteration=current_iteration,
                total=total_iterations or 0,
                result=result,
            )

            # 迭代间隔
            if exec_cfg.interval_ms > 0:
                time.sleep(exec_cfg.interval_ms / 1000)

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
                # 关闭后台执行线程（也会自动关闭 Context/SessionStore）
                executor.shutdown()
            except Exception as e:
                logger.log_session_error(f"Warning: Error shutting down executor: {e}")

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
            template_dict.get("ConfigForDevices", {}), template_dict.get("Devices", [])
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
                    # merge into underlying mapping
                    if hasattr(command_device_dict, "dict"):
                        command_device_dict.dict[key] = value
                    else:
                        # Fallback: update the dict representation if available
                        if isinstance(command_device_dict, dict):
                            command_device_dict[key] = value

            # Sort commands by order but preserve original sequence for same order values
            cdd_dict: Any = (
                command_device_dict.dict
                if hasattr(command_device_dict, "dict")
                else command_device_dict
            )
            commands = sorted(
                enumerate(cdd_dict["Commands"]),
                key=lambda x: (
                    x[1]["order"],
                    x[0],
                ),  # Sort by order first, then by original index
            )
            commands = [cmd[1] for cmd in commands]  # Extract just the commands

            if "ConfigForCommands" in cdd_dict:
                apply_configs_for_commands(
                    cdd_dict.get("ConfigForCommands", {}),
                    cdd_dict,
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

        logger.log_session_end(
            (
                f"{'✅ ' + str(len(files) - failure_count) + '/' + str(len(files))} files passed."
                if failure_count == 0
                else f"❌ {failure_count}/{len(files)} files failed."
            )
        )


def monitor_folder(folder_path, file_queue, stop_event):
    """
    Monitor a folder for new configuration files (JSON or YAML) and add them to the execution queue.
    """
    logger.log_session_info(f"Starting to monitor folder: {folder_path}")

    # 用于跟踪已处理文件的执行配置数据，键为文件路径，值为(修改时间, 内容哈希)元组
    processed_files = {}

    # 确保文件夹存在
    if not os.path.exists(folder_path):
        logger.log_session_info(f"Folder '{folder_path}' does not exist. Creating it.")
        os.makedirs(folder_path)

    while not stop_event.is_set():
        try:
            # 获取文件夹中的所有配置文件（JSON 和 YAML）
            config_files = [
                f
                for f in os.listdir(folder_path)
                if f.endswith((".json", ".yaml", ".yml"))
            ]

            # 遍历文件，检查是否有新增或修改的文件
            from pathlib import Path

            for file_name in config_files:
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
                        dict_data.get("Devices", []),
                    )

                command_device_dict = CommandDeviceDict(dict_data)

                # Save the dict content to a file in the log_date_dir
                from pathlib import Path

                dict_filename = Path(file_path).name
                output_file_path = (
                    Path(command_device_dict.log_date_dir) / dict_filename
                )

                try:
                    _save_dict(dict_data, output_file_path)
                    logger.log_session_start(f"Dictionary saved to {output_file_path}")
                except Exception as e:
                    logger.log_session_error(f"Error saving dictionary to file: {e}")

                # Sort commands by order but preserve original sequence for same order values
                cdd_dict: Any = (
                    command_device_dict.dict
                    if hasattr(command_device_dict, "dict")
                    else command_device_dict
                )
                commands = sorted(
                    enumerate(cdd_dict["Commands"]),
                    key=lambda x: (
                        x[1]["order"],
                        x[0],
                    ),
                )
                commands = [cmd[1] for cmd in commands]

                if "ConfigForCommands" in cdd_dict:
                    apply_configs_for_commands(
                        cdd_dict.get("ConfigForCommands", {}),
                        cdd_dict,
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
                        # 关闭后台执行线程（也会自动关闭 Context/SessionStore）
                        executor.shutdown()
                    except Exception as e:
                        logger.log_session_error(f"Error shutting down executor: {e}")

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
