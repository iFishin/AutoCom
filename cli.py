"""AutoCom CLI 入口"""

import sys
import os
import json
import time
import argparse
from components.Logger import AutoComLogger

# 根据运行方式选择导入路径
try:
    from utils.dirs import get_dirs
    from utils.common import CommonUtils
    from AutoCom import (
        execute_with_loop,
        execute_with_folder,
        ensure_working_directories,
        monitor_folder,
        process_file_queue,
    )
    from version import __version__
except ModuleNotFoundError:
    from .utils.dirs import get_dirs
    from .utils.common import CommonUtils
    from .AutoCom import (
        execute_with_loop,
        execute_with_folder,
        ensure_working_directories,
        monitor_folder,
        process_file_queue,
    )
    from .version import __version__

# 获取路径管理对象（此时不创建目录）
dirs = get_dirs()
# 初始化 Logger（这是 cli.py 的唯一初始化点）
log_file = str(dirs.session_dir / "EXECUTION.log")
logger = AutoComLogger.get_instance(name="AutoCom", log_file=log_file)

def main():
    """CLI 入口函数"""
    run_main()


def run_main():
    """主程序入口函数,用于被 CLI 调用"""

    # 在初始化目录之前检查参数，避免不传参数时创建目录
    if len(sys.argv) == 1:
        # 显示欢迎信息
        print()
        print(f"🚀 AutoCom v{__version__}")
        print("   串口自动化指令执行工具 - 支持多设备、多指令的串行和并行执行")
        print()
        print("🎯 初始化执行目录:")
        print(
            "   autocom --init                      # 在当前目录创建执行结构和示例文件"
        )
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

    parser = argparse.ArgumentParser(
        description="AutoCom command execution tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  autocom -d dict.json -l 3              # 循环执行3次\n"
        "  autocom -d dict.json -i                # 无限循环\n"
        "  autocom -f dicts/                      # 文件夹模式\n"
        "  autocom -m temps/                      # 监控模式\n"
        "  autocom -d dict.json -c config.json    # 使用配置文件\n",
    )

    # 添加版本参数
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"AutoCom v{__version__}",
        help="Show version information and exit",
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

    args = parser.parse_args()

    # 处理 --init 参数
    if args.init:
        logger.log_info("🚀 Initializing AutoCom project structure...")

        try:
            # 初始化项目结构
            dirs.init_project_structure()

            logger.log_info(
                "✨ Initialization complete! You can now use AutoCom in this directory."
            )
            logger.log_info("💡 Tip: Edit files in dicts/ to customize your commands")
            logger.log_info("💡 Tip: Run 'autocom -d dicts/dict.json -l 3' to test")

        except Exception as e:
            logger.log_info(f"❌ Error during initialization: {e}")
            sys.exit(1)

        sys.exit(0)

    # 初始化 config 变量（防止未定义错误）
    config = None
    config_path = None

    if args.config:
        # 使用 dirs 辅助方法获取配置文件路径
        config_file_path = dirs.get_config_path(args.config)

        try:
            with open(config_file_path, "r") as file:
                config = json.load(file)
        except FileNotFoundError:
            logger.log_info(f"Error: Config file '{config_file_path}' not found")
            sys.exit(1)
        except json.JSONDecodeError:
            logger.log_info(f"Error: Invalid JSON format in '{config_file_path}'")
            sys.exit(1)

    # 【提前初始化 Logger】在所有分支之前，确保所有路径都能使用
    # 显式创建工作目录
    device_logs_dir = str(dirs.device_logs_dir)
    temps_dir = str(dirs.temp_dir)
    data_store_dir = str(dirs.data_store_dir)

    # 初始化 CommonUtils 日志路径（在创建了 device_logs 目录后）
    CommonUtils.init_log_file_path(str(dirs.session_dir))



    if args.dict:
        # 使用 dirs 辅助方法获取字典文件路径（优先从工作目录，再从包目录）
        dict_path = dirs.get_dict_path(args.dict)

        start_time = time.time()
        try:
            execute_with_loop(str(dict_path), args.loop, args.infinite, config)
        except KeyboardInterrupt:
            logger.log_info("Execution interrupted by user")
        except FileNotFoundError as e:
            logger.log_info(f"Error: Dictionary file not found: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.log_info(f"Error: Invalid JSON format: {e}")
            sys.exit(1)
        finally:
            end_time = time.time()
            execution_time = end_time - start_time
            hours = int(execution_time // 3600)
            minutes = int((execution_time % 3600) // 60)
            seconds = execution_time % 60
            logger.log_info(
                f"Total execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f}"
            )
    elif args.folder:
        # 使用 dirs 辅助方法获取文件夹路径（优先从工作目录，再从包目录）
        folder_path = str(dirs.get_folder_path(args.folder))

        import re

        json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
        sorted_files = sorted(
            json_files,
            key=lambda x: (
                int(re.match(r"(\d+)", x).group(1))
                if re.match(r"(\d+)", x)
                else float("inf")
            ),
        )

        start_time = time.time()
        try:
            execute_with_folder(folder_path, sorted_files, config)
        except KeyboardInterrupt:
            logger.log_info("Execution interrupted by user")
        except FileNotFoundError as e:
            logger.log_info(f"Error: Folder or file not found: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.log_info(f"Error: Invalid JSON format: {e}")
            sys.exit(1)
        finally:
            end_time = time.time()
            execution_time = end_time - start_time
            hours = int(execution_time // 3600)
            minutes = int((execution_time % 3600) // 60)
            seconds = execution_time % 60
            logger.log_info(
                f"Total execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f}"
            )


if __name__ == "__main__":
    main()
