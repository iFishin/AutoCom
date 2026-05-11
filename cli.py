"""AutoCom CLI 入口"""

import sys
import os
import json
import time
import argparse
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
from components.Logger import AutoComLogger

# 获取路径管理对象
dirs = get_dirs()
# 初始化 Logger
log_file = str(dirs.session_dir / "EXECUTION.log")
logger = AutoComLogger(log_file)

def main():
    """CLI 入口函数"""
    run_main()


def run_main():
    """主程序入口函数,用于被 CLI 调用"""

    if len(sys.argv) == 1:
        # 显示欢迎信息（含艺术字）
        autocom_text_art = """
 ▄▄▄▄▄▄▄ ▄▄   ▄▄ ▄▄▄▄▄▄▄ ▄▄▄▄▄▄▄ ▄▄▄▄▄▄▄ ▄▄▄▄▄▄▄ ▄▄   ▄▄ 
█       █  █ █  █       █       █       █       █  █▄█  █
█   ▄   █  █ █  █▄     ▄█   ▄   █       █   ▄   █       █
█  █▄█  █  █▄█  █ █   █ █  █ █  █     ▄▄█  █ █  █       █
█       █       █ █   █ █  █▄█  █    █  █  █▄█  █       █
█   ▄   █       █ █   █ █       █    █▄▄█       █ ██▄██ █
█▄▄█ █▄▄█▄▄▄▄▄▄▄█ █▄▄▄█ █▄▄▄▄▄▄▄█▄▄▄▄▄▄▄█▄▄▄▄▄▄▄█▄█   █▄█
        """

        print(autocom_text_art)
        print(f"AutoCom v{__version__}")
        print("串口自动化指令执行工具 - 支持多设备、多指令的串行和并行执行")
        print()
        print("🎯 初始化执行目录:")
        print(
            "   autocom --init                      # 在当前目录创建执行结构和示例文件"
        )
        print()
        print("📖 快速开始:")
        print("   autocom -d dict.yaml -l 3           # 执行字典文件，循环3次")
        print("   autocom -d dict.yaml -i             # 无限循环模式")
        print("   autocom -f dicts/                   # 执行文件夹内所有字典")
        print("   autocom -m temps/                   # 监控模式")
        print()
        print("✨ 选项说明")
        print()
        print("  --cli-output-mode  指定 CLI 日志输出方式: 'table' 或 'plain' (默认: 'table')")
        print()
        print("🧭 MCP Server (AI Agent 接口)")
        print("   autocom mcp                                           # 启动 stdio 模式（默认，适合 Claude Desktop）")
        print("   autocom mcp --sse                                     # 启动 SSE (HTTP) 模式（适合远端/服务器）")
        print("   autocom mcp --sse --port 8888 --host 0.0.0.0          # 在所有接口上监听")
        print("   autocom mcp --streamable                              # 启动 Streamable HTTP 模式（适合需要持续双向消息流的客户端）")
        print("   autocom mcp --streamable --port 8888 --host 0.0.0.0   # 在所有接口上监听")
        print()
        print("📚 文档: https://github.com/iFishin/AutoCom")
        print()
        print("🔍 更多帮助:")
        print("   autocom --help                      # 查看完整帮助")
        print("   autocom -v                          # 查看版本信息")
        print()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="AutoCom command execution tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  autocom -d dict.yaml -l 3              # 循环执行3次\n"
        "  autocom -d dict.yaml -i                # 无限循环\n"
        "  autocom -f dicts/                      # 文件夹模式\n"
        "  autocom -m temps/                      # 监控模式\n"
        "  autocom -d dict.yaml -c config.yaml    # 使用配置文件\n",
    )

    # 添加版本参数
    # MCP Server 子命令
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    mcp_parser = subparsers.add_parser(
        "mcp",
        help="启动 MCP Server（为 AI Agent 提供串口操作接口）",
        epilog="""
示例:
  autocom mcp                              # stdio 模式（默认，适合 Claude Desktop）
  autocom mcp --sse                        # SSE (HTTP) 模式
  autocom mcp --sse --port 8080            # 自定义端口
  autocom mcp --sse --host 127.0.0.1       # 仅本地访问
  autocom mcp --streamable                 # Streamable HTTP 模式
  autocom mcp --streamable --port 8080     # 自定义端口
  autocom mcp --streamable --host 127.0.0.1 # 仅本地访问
    autocom mcp --streamable --port 8888 --auth-key s3cr3t  # 启用 API Key 鉴权
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mcp_parser.add_argument(
        "--sse",
        action="store_true",
        help="以 SSE (HTTP) 模式运行（默认: stdio 模式）",
    )
    mcp_parser.add_argument(
        "--streamable",
        action="store_true",
        help="以 Streamable HTTP 模式运行（长连接/双向通道）",
    )
    mcp_parser.add_argument(
        "--auth-key",
        type=str,
        help="为 SSE/Streamable 启用简单 API Key 鉴权（Header: Authorization: Bearer <key> or X-API-Key）",
    )
    mcp_parser.add_argument(
        "--port",
        type=int,
        default=8888,
        help="SSE 模式下的监听端口（默认: 8888）",
    )
    mcp_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="SSE 模式下的监听地址（默认: 0.0.0.0）",
    )

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

    parser.add_argument(
        "--cli-output-mode",
        choices=["table", "plain"],
        default="table",
        help="CLI logging output mode: table or plain (default: table)",
    )

    args = parser.parse_args()

    # 处理子命令
    if args.command == "mcp":
        from components.MCPServer import main as mcp_main
        # 构建要传递给 MCPServer 的 argv 列表
        sys.argv = [sys.argv[0]]
        if args.sse:
            sys.argv.append("--sse")
        elif args.streamable:
            sys.argv.append("--streamable")

        # 传递端口和 host（无论 SSE 还是 Streamable 都适用）
        if args.sse or args.streamable:
            sys.argv.extend(["--port", str(args.port), "--host", args.host])

        # 传递鉴权 key（可选）
        if getattr(args, "auth_key", None):
            sys.argv.extend(["--auth-key", args.auth_key])

        mcp_main()
        return
    
    # 初始化 Logger（现在可以使用 CLI 参数指定输出模式）
    logger = AutoComLogger.get_instance(
        name="AutoCom", log_file=log_file, cli_output_mode=args.cli_output_mode
    )

    # 处理 --init 参数
    if args.init:
        logger.log_session_start("🚀 Initializing AutoCom project structure...")

        try:
            # 初始化项目结构
            dirs.init_project_structure()

            logger.log_session_start(
                "✨ Initialization complete! You can now use AutoCom in this directory."
            )
            logger.log_session_start(
                "💡 Tip: Edit files in dicts/ to customize your commands"
            )
            logger.log_session_start(
                "💡 Tip: Run 'autocom -d dicts/dict.json -l 3' to test"
            )

        except Exception as e:
            logger.log_session_error(f"❌ Error during initialization: {e}")
            sys.exit(1)

        sys.exit(0)

    # 初始化 config 变量（防止未定义错误）
    config: dict = {}
    config_path = None

    if args.config:
        # 使用 dirs 辅助方法获取配置文件路径
        config_file_path = dirs.get_config_path(args.config)

        try:
            with open(config_file_path, "r") as file:
                loaded_config = json.load(file)
            if not isinstance(loaded_config, dict):
                raise ValueError("Config file must contain a JSON object")
            config = loaded_config
        except FileNotFoundError:
            logger.log_session_error(
                f"Error: Config file '{config_file_path}' not found"
            )
            sys.exit(1)
        except json.JSONDecodeError:
            logger.log_session_error(
                f"Error: Invalid JSON format in '{config_file_path}'"
            )
            sys.exit(1)
        except ValueError as e:
            logger.log_session_error(f"Error: {e}")
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
            logger.log_session_info("Execution interrupted by user")
        except FileNotFoundError as e:
            logger.log_session_error(f"Error: Dictionary file not found: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.log_session_error(f"Error: Invalid JSON format: {e}")
            sys.exit(1)
        finally:
            end_time = time.time()
            execution_time = end_time - start_time
            hours = int(execution_time // 3600)
            minutes = int((execution_time % 3600) // 60)
            seconds = execution_time % 60
            logger.log_session_info(
                f"Total execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f}"
            )
    elif args.folder:
        # 使用传入的文件夹路径，支持相对路径和绝对路径
        folder_path = os.path.abspath(args.folder)

        import re

        config_files = [f for f in os.listdir(folder_path) if f.endswith((".json", ".yaml", ".yml"))]

        def _sort_key(x):
            match = re.match(r"(\d+)", x)
            return int(match.group(1)) if match else float("inf")

        sorted_files = sorted(config_files, key=_sort_key)

        start_time = time.time()
        try:
            execute_with_folder(folder_path, sorted_files, config)
        except KeyboardInterrupt:
            logger.log_session_info("Execution interrupted by user")
        except FileNotFoundError as e:
            logger.log_session_error(f"Error: Folder or file not found: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.log_session_error(f"Error: Invalid JSON format: {e}")
            sys.exit(1)
        finally:
            end_time = time.time()
            execution_time = end_time - start_time
            hours = int(execution_time // 3600)
            minutes = int((execution_time % 3600) // 60)
            seconds = execution_time % 60
            logger.log_session_info(
                f"Total execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f}"
            )


if __name__ == "__main__":
    main()
