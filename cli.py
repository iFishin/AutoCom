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


def _open_studio(port: int = 0):
    """启动 Pipeline 可视化编辑器。"""
    import webbrowser
    from pathlib import Path

    # studio/index.html 相对于此文件所在目录
    studio_html = Path(__file__).resolve().parent / "studio" / "index.html"

    if not studio_html.exists():
        print(f"❌ 未找到: {studio_html}")
        sys.exit(1)

    if port > 0:
        # HTTP 服务模式（可跨设备访问）
        print(f"🌐 Starting AutoCom Studio on http://localhost:{port}")
        print("   Press Ctrl+C to stop")
        webbrowser.open(f"http://localhost:{port}")
        import http.server
        import socketserver
        os.chdir(studio_html.parent)
        with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nStopped.")
    else:
        # 直接打开本地文件
        url = studio_html.as_uri()
        webbrowser.open(url)
        print(f"📋 AutoCom Studio 已打开")
        print(f"   URL: {url}")


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
        print(f"  AutoCom v{__version__} — 通用流水线自动化执行工具")
        print(f"  {'─' * 50}")
        print()
        print("  🚀  执行流水线:")
        print(f"    autocom -p pipeline.yaml        {'执行流水线文件 (YAML/JSON)'}")
        print(f"    autocom -p pipeline.yaml -n 5   {'覆盖循环次数'}")
        print()
        print("  📂  批量执行:")
        print(f"    autocom -f dicts/               {'执行文件夹内所有配置文件'}")
        print(f"    autocom -m temps/               {'监控模式 (新文件自动执行)'}")
        print()
        print("  🔧  初始化 & 查看:")
        print(f"    autocom --init                  {'在当前目录创建示例结构和配置'}")
        print(f"    autocom -v                      {'查看版本号'}")
        print(f"    autocom --help                  {'查看完整参数说明'}")
        print()
        print("  🌐  MCP Server (AI Agent 接口):")
        print(f"    autocom mcp                     {'启动 stdio 模式 (Claude Desktop)'}")
        print(f"    autocom mcp --sse               {'启动 SSE (HTTP/Socket)'}")
        print(f"    autocom mcp --streamable        {'启动 Streamable HTTP'}")
        print()
        print("  🌍  REST API (HTTP 接口):")
        print(f"    autocom api                     {'启动 REST API (端口 8000)'}")
        print(f"    autocom api --port 8080         {'自定义端口'}")
        print(f"    autocom api --host 127.0.0.1    {'仅本地访问'}")
        print()
        print(f"  {'─' * 50}")
        print("  📖  完整文档: https://github.com/iFishin/AutoCom")
        print()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="AutoCom — 通用流水线自动化执行工具（串口 / HTTP / 脚本 / 混合）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""用法示例:

  # 执行流水线（推荐新格式）
  autocom -p pipeline.yaml              # Config 块决定执行方式
  autocom -p pipeline.yaml -n 5         # 覆盖执行轮数
  autocom -p pipeline.yaml --duration 10m   # 限时 10 分钟
  autocom -p pipeline.yaml -n 100 --duration 30s  # 先到先停

  # 兼容旧格式
  autocom -d dict.yaml                  # 自动识别旧 Commands 格式

  # 批量模式
  autocom -f dicts/                     # 执行文件夹内所有文件
  autocom -m temps/                     # 监控文件夹，自动执行新文件

  # 输出格式
  autocom -p pipeline.yaml --cli-output-mode plain   # 纯文本输出
""",
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

    # ── studio 子命令 ──
    studio_parser = subparsers.add_parser(
        "studio",
        help="启动 Pipeline 可视化编辑器（浏览器中打开）",
        epilog="""用法:
  autocom studio              # 在浏览器中打开可视化编辑器
  autocom studio --port 8080  # 启动 HTTP 服务模式（可选）
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    studio_parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="以 HTTP 服务模式运行（可选，默认直接打开本地文件）",
    )

    # ── api 子命令 ──
    api_parser = subparsers.add_parser(
        "api",
        help="启动 REST API Server（提供 HTTP 接口，含 Swagger UI）",
        epilog="""示例:
  autocom api                            # 默认 8000 端口
  autocom api --port 8080                # 自定义端口
  autocom api --host 127.0.0.1           # 仅本地访问
  autocom api --port 8080 --host 0.0.0.0 # 所有网络接口
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    api_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="监听端口（默认: 8000）",
    )
    api_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="监听地址（默认: 0.0.0.0，也可设为 127.0.0.1 仅本地访问）",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"AutoCom v{__version__}",
        help="显示版本号",
    )

    group1 = parser.add_mutually_exclusive_group()
    group1.add_argument(
        "-p",
        "--pipeline",
        dest="dict",
        type=str,
        help="流水线配置文件路径（YAML/JSON，推荐格式）",
    )
    group1.add_argument(
        "-d",
        "--dict",
        dest="dict",
        type=str,
        help=argparse.SUPPRESS,  # 隐藏，向后兼容
    )
    group1.add_argument(
        "-f",
        "--folder",
        type=str,
        help="批量执行文件夹内所有配置文件",
    )

    parser.add_argument(
        "-n",
        "--iterations",
        dest="loop",
        default=None,
        type=int,
        help="循环执行轮数（覆盖 Config 块设置）",
    )
    parser.add_argument(
        "-l",
        "--loop",
        dest="loop",
        default=None,
        type=int,
        help=argparse.SUPPRESS,  # 隐藏，旧别名保留兼容
    )
    parser.add_argument(
        "--duration",
        default=None,
        type=str,
        help="目标执行时长，到达后自动停止。格式: 30(秒), 30s, 5m(分), 1h(时)",
    )
    parser.add_argument(
        "-i",
        "--infinite",
        action="store_true",
        help="无限循环模式（Ctrl+C 停止）",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help=argparse.SUPPRESS,  # 已废弃，功能由 Config 块替代
    )
    parser.add_argument(
        "-m",
        "--monitor",
        type=str,
        help="监控模式：监听文件夹，新文件自动执行",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="在当前目录创建示例配置和目录结构",
    )

    parser.add_argument(
        "--cli-output-mode",
        choices=["table", "plain"],
        default="table",
        help="日志输出格式: table（表格）| plain（纯文本，默认 table）",
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

    # studio 子命令
    if args.command == "studio":
        _open_studio(args.port)
        return

    # api 子命令
    if args.command == "api":
        try:
            from components.RESTServer import main as api_main
        except ImportError as e:
            print(f"Error: {e}")
            print("Please install dependencies: pip install fastapi uvicorn")
            raise SystemExit(1)
        sys.argv = [sys.argv[0], "--port", str(args.port), "--host", args.host]
        api_main()
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
                "💡 Tip: Run 'autocom -p dicts/dict.json' to test"
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

    # 初始化 CommonUtils 日志路径（在创建了 device_logs 目录后）
    CommonUtils.init_log_file_path(str(dirs.session_dir))

    # ── 旧参数废弃警告 ──
    # 检查是否使用了旧式参数（-d 仍可用，-c 已废弃）
    _old_args_used = []
    # 检测 -d 被使用：当 -p 为空且 -d 有值时
    if hasattr(args, 'dict') and args.dict and not any(
        a in sys.argv for a in ['-p', '--pipeline']
    ):
        pass  # -d 仍兼容，不警告
    if args.config:
        logger.log_session_warning(
            "⚠️  -c/--config 参数已废弃，执行配置请直接在配置文件的 Config 块中声明"
        )
    if args.infinite:
        logger.log_session_warning(
            "ℹ️  -i/--infinite 仍可用，但建议在配置文件的 Config 块中声明 mode: infinite"
        )

    if args.dict:
        # 使用 dirs 辅助方法获取执行配置文件路径（优先从工作目录，再从包目录）
        dict_path = dirs.get_dict_path(args.dict)

        start_time = time.time()
        try:
            execute_with_loop(str(dict_path), args.loop, args.infinite, config, duration=args.duration)
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
