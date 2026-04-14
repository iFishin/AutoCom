#!/usr/bin/env python3
"""
AutoCom 开发工具

统一的开发、测试、打包工具
用法: python -m scripts.dev [命令]
      dev [命令]  (安装后)
      make dev-[命令]
"""

import sys
import os
import subprocess
import shutil
import re
import argparse
import glob
from pathlib import Path
from typing import Optional, List, Tuple, Union

# 项目根目录 (scripts/ 的父目录)
ROOT_DIR = Path(__file__).parent.parent.absolute()
VERSION_FILE = ROOT_DIR / "version.py"


# 颜色输出
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    END = "\033[0m"
    BOLD = "\033[1m"


# 版本号正则
VERSION_PATTERN = r"^\d+\.\d+\.\d+$"

# 构建清理模式
CLEAN_PATTERNS = [
    "build",
    "dist",
    "*.egg-info",
]


def print_header(text: str) -> None:
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")


def print_success(text: str) -> None:
    """打印成功信息"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str) -> None:
    """打印错误信息"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text: str) -> None:
    """打印警告信息"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_info(text: str) -> None:
    """打印信息"""
    print(f"{Colors.BLUE}→ {text}{Colors.END}")


def run_command(
    cmd: str, check: bool = True, capture: bool = False, cwd: Optional[Path] = None
) -> Union[str, bool, None]:
    """运行命令

    Args:
        cmd: 要执行的命令
        check: 是否在失败时抛出异常
        capture: 是否捕获输出
        cwd: 工作目录

    Returns:
        如果 capture=True，返回命令输出（失败返回 None）
        如果 capture=False，返回 True/False
    """
    if cwd is None:
        cwd = ROOT_DIR

    try:
        result = subprocess.run(
            cmd, shell=True, check=False, cwd=cwd, capture_output=capture, text=True
        )

        if result.returncode != 0:
            if result.stderr:
                print(result.stderr)
            if check:
                raise subprocess.CalledProcessError(result.returncode, cmd)
            return None if capture else False

        if capture:
            return result.stdout.strip() if result.stdout.strip() else None
        return True

    except subprocess.CalledProcessError:
        return None if capture else False


def get_current_version() -> Optional[str]:
    """获取当前版本"""
    if not VERSION_FILE.exists():
        return None

    content = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__ = ["\']([^"\']+)["\']', content)
    return match.group(1) if match else None


def set_version(new_version: str) -> bool:
    """设置新版本"""
    if not VERSION_FILE.exists():
        print_error(f"找不到 {VERSION_FILE}")
        return False

    content = VERSION_FILE.read_text(encoding="utf-8")
    content = re.sub(
        r'__version__ = ["\']([^"\']+)["\']', f'__version__ = "{new_version}"', content
    )
    VERSION_FILE.write_text(content, encoding="utf-8")
    return True


def clean() -> bool:
    """清理构建产物"""
    print_header("清理构建产物")

    removed_count = 0

    for pattern in CLEAN_PATTERNS:
        path = ROOT_DIR / pattern
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
                print_success(f"删除 {pattern}/")
            else:
                path.unlink()
                print_success(f"删除 {pattern}")
            removed_count += 1

    # 处理递归模式
    recursive_patterns = [
        ("**/__pycache__", "目录"),
        ("**/*.pyc", "文件"),
        ("**/*.pyo", "文件"),
    ]

    for pattern, type_name in recursive_patterns:
        for path in glob.glob(str(ROOT_DIR / pattern), recursive=True):
            path_obj = Path(path)
            try:
                if path_obj.is_dir():
                    shutil.rmtree(path_obj)
                else:
                    path_obj.unlink()
                print_success(f"删除 {path_obj.relative_to(ROOT_DIR)}")
                removed_count += 1
            except (FileNotFoundError, PermissionError):
                pass

    # 清理特定文件和目录
    extra_paths = [".pytest_cache", ".coverage"]
    for name in extra_paths:
        path = ROOT_DIR / name
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print_success(f"删除 {name}")
            removed_count += 1

    print_success(f"清理完成 ({removed_count} 项)")
    return True


def _run_import_test(test_name: str, test_code: str) -> Tuple[bool, str]:
    """运行导入测试

    Returns:
        (是否成功, 结果信息)
    """
    result = run_command(
        f'"{sys.executable}" -c "{test_code}"', check=False, capture=True
    )
    if result and isinstance(result, str):
        return (True, result)
    return (False, "")


def test() -> bool:
    """运行测试"""
    print_header("运行测试")

    tests: List[Tuple[str, str]] = [
        ("导入主模块", "import AutoCom; print('OK')"),
        ("导入版本", "import version; print(version.__version__)"),
        (
            "导入组件",
            "from components import CommandDeviceDict, CommandExecutor, DataStore, Device; print('OK')",
        ),
        (
            "导入工具",
            "from utils import CommonUtils, ActionHandler, CustomActionHandler; print('OK')",
        ),
        ("CLI模块", "import cli; print('OK')"),
    ]

    passed = 0
    failed = 0

    for test_name, test_code in tests:
        success, result = _run_import_test(test_name, test_code)
        if success:
            print_success(f"{test_name}: {result}")
            passed += 1
        else:
            print_error(f"{test_name}: 失败")
            failed += 1

    print(f"\n总计: {passed}/{len(tests)} 测试通过")

    # 测试 CLI 命令
    print("\n检查 CLI 命令...")

    cli_tests = [
        (["autocom", "-v"], "autocom 命令"),
        ([sys.executable, "-m", "cli", "-v"], "CLI 模块 (python -m)"),
    ]

    cli_passed = False
    for cmd, name in cli_tests:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=ROOT_DIR, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                print_success(f"{name}: {result.stdout.strip()}")
                cli_passed = True
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if not cli_passed:
        print_warning("autocom 命令未安装 (运行 'dev install' 安装)")

    return failed == 0


def build() -> bool:
    """构建分发包"""
    print_header("构建分发包")

    # 确保安装了 build
    print_info("检查构建工具...")
    try:
        import build as _  # noqa: F401
    except ImportError:
        print_warning("未安装 build 模块,正在安装...")
        run_command(f'"{sys.executable}" -m pip install build')

    # 清理旧的构建
    clean()

    # 构建
    print_info("开始构建...")
    if run_command(f'"{sys.executable}" -m build'):
        print_success("构建成功!")

        dist_dir = ROOT_DIR / "dist"
        if dist_dir.exists():
            print("\n生成的包:")
            for file in dist_dir.iterdir():
                size = file.stat().st_size / 1024
                print(f"   - {file.name} ({size:.1f} KB)")
        return True
    else:
        print_error("构建失败")
        return False


def install_dev() -> bool:
    """开发模式安装"""
    print_header("开发模式安装")

    print_info("以开发模式安装 AutoCom...")
    if run_command(f'"{sys.executable}" -m pip install -e .'):
        print_success("安装成功!")

        # 验证安装
        if test():
            print_success("安装验证通过")
            return True
        else:
            print_error("安装验证失败")
            return False
    else:
        print_error("安装失败")
        return False


def version_cmd(new_version: Optional[str] = None) -> bool:
    """管理版本"""
    print_header("版本管理")

    current = get_current_version()
    if current:
        print_info(f"当前版本: {current}")
    else:
        print_error("无法读取当前版本")
        return False

    if not new_version:
        return True

    # 验证版本格式
    if not re.match(VERSION_PATTERN, new_version):
        print_error(f"版本号格式不正确: {new_version}")
        print_info("正确格式: x.y.z (例如: 1.0.1, 1.2.3)")

        # 检测常见错误
        if "," in new_version:
            print_warning(f"检测到逗号,应该使用点号: {new_version.replace(',', '.')}")

        return False

    # 确认更新
    print(f"\n{Colors.YELLOW}将版本从 {current} 更新到 {new_version}{Colors.END}")
    response = input("确认? [y/N]: ")
    if response.lower() not in ["y", "yes"]:
        print_warning("已取消")
        return False

    # 更新版本
    if set_version(new_version):
        print_success(f"版本已更新: {current} -> {new_version}")

        print("\n后续步骤:")
        print("  1. git add version.py")
        print(f'  2. git commit -m "Bump version to v{new_version}"')
        print(f"  3. git tag v{new_version}")
        print(f"  4. git push && git push origin v{new_version}")
        return True
    else:
        print_error("版本更新失败")
        return False


def publish() -> bool:
    """发布到 PyPI"""
    print_header("发布到 PyPI")

    # 检查 twine
    print_info("检查发布工具...")
    import importlib.util
    if importlib.util.find_spec("twine") is None:
        print_warning("未安装 twine,正在安装...")
        run_command(f'"{sys.executable}" -m pip install twine')

    # 检查 dist 目录
    dist_dir = ROOT_DIR / "dist"
    if not dist_dir.exists() or not list(dist_dir.iterdir()):
        print_error("没有找到构建产物")
        print_info("请先运行: dev build")
        return False

    # 列出文件
    print("\n待发布文件:")
    for file in dist_dir.iterdir():
        print(f"   - {file.name}")

    # 确认
    print(f"\n{Colors.YELLOW}准备发布到 PyPI{Colors.END}")
    response = input("确认? [y/N]: ")
    if response.lower() not in ["y", "yes"]:
        print_warning("已取消")
        return False

    # 上传
    print_info("上传到 PyPI...")
    if run_command(f'"{sys.executable}" -m twine upload dist/* --disable-progress-bar'):
        print_success("发布成功!")

        current = get_current_version()
        if current:
            print(f"\nAutoCom v{current} 已发布到 PyPI!")
            print(f"   用户可以通过以下命令安装:")
            print(f"   pip install autocom=={current}")
        return True
    else:
        print_error("发布失败")
        return False


def create_parser() -> argparse.ArgumentParser:
    """创建命令行解析器"""
    parser = argparse.ArgumentParser(
        description="AutoCom 开发工具 - 统一的开发、测试、打包工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  dev clean              清理构建产物
  dev test               运行测试
  dev build              构建分发包
  dev install            开发模式安装
  dev version            查看当前版本
  dev version 1.1.0      更新版本号
  dev publish            发布到 PyPI

常用工作流:
  1. 开发:
     dev install    # 开发模式安装
     dev test       # 运行测试
  
  2. 发布新版本:
     dev version 1.1.0    # 更新版本号
     dev test             # 测试
     dev build            # 构建
     dev publish          # 发布到 PyPI
  
  3. 本地测试:
     dev build
     pip install --force-reinstall dist/autocom-*.whl
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # clean 命令
    subparsers.add_parser("clean", help="清理构建产物")

    # test 命令
    subparsers.add_parser("test", help="运行测试")

    # build 命令
    subparsers.add_parser("build", help="构建分发包")

    # install 命令
    subparsers.add_parser("install", help="开发模式安装")

    # version 命令
    version_parser = subparsers.add_parser("version", help="版本管理")
    version_parser.add_argument("new_version", nargs="?", help="新版本号 (格式: x.y.z)")

    # publish 命令
    subparsers.add_parser("publish", help="发布到 PyPI")

    return parser


def main() -> int:
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 如果没有子命令，显示帮助
    if not args.command:
        parser.print_help()
        return 0

    # 命令映射
    commands = {
        "clean": clean,
        "test": test,
        "build": build,
        "install": install_dev,
        "publish": publish,
    }

    if args.command == "version":
        success = version_cmd(args.new_version)
        return 0 if success else 1
    elif args.command in commands:
        result = commands[args.command]()
        return 0 if result or result is None else 1
    else:
        print_error(f"未知命令: {args.command}")
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
