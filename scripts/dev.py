#!/usr/bin/env python3
"""
AutoCom 开发工具

统一的开发、测试、打包工具
用法: python dev.py [命令]
"""
import sys
import os
import subprocess
import shutil
import re
from pathlib import Path

# 项目根目录 (scripts/ 的父目录)
ROOT_DIR = Path(__file__).parent.parent.absolute()
VERSION_FILE = ROOT_DIR / "version.py"

# 颜色输出
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text):
    """打印成功信息"""
    print(f"{Colors.GREEN}OK {text}{Colors.END}")

def print_error(text):
    """打印错误信息"""
    print(f"{Colors.RED}NG {text}{Colors.END}")

def print_warning(text):
    """打印警告信息"""
    print(f"{Colors.YELLOW}!! {text}{Colors.END}")

def print_info(text):
    """打印信息"""
    print(f"{Colors.BLUE}:: {text}{Colors.END}")

def run_command(cmd, check=True, capture=False):
    """运行命令"""
    try:
        if capture:
            result = subprocess.run(cmd, shell=True, check=False, 
                                  capture_output=True, text=True, cwd=ROOT_DIR)
            if result.returncode != 0:
                return None
            return result.stdout.strip() if result.stdout.strip() else None
        else:
            result = subprocess.run(cmd, shell=True, check=False, cwd=ROOT_DIR,
                                  capture_output=True, text=True)
            if result.returncode != 0:
                if result.stderr:
                    print(result.stderr)
                if check:
                    raise subprocess.CalledProcessError(result.returncode, cmd)
                return False
            return True
    except subprocess.CalledProcessError as e:
        if capture:
            return None
        return False

def get_current_version():
    """获取当前版本"""
    if not VERSION_FILE.exists():
        return None
    
    content = VERSION_FILE.read_text(encoding='utf-8')
    match = re.search(r'__version__ = ["\']([^"\']+)["\']', content)
    return match.group(1) if match else None

def set_version(new_version):
    """设置新版本"""
    if not VERSION_FILE.exists():
        print_error(f"找不到 {VERSION_FILE}")
        return False
    
    content = VERSION_FILE.read_text(encoding='utf-8')
    content = re.sub(
        r'__version__ = ["\']([^"\']+)["\']',
        f'__version__ = "{new_version}"',
        content
    )
    VERSION_FILE.write_text(content, encoding='utf-8')
    return True

def clean():
    """清理构建产物"""
    print_header("清理构建产物")
    
    patterns = [
        'build',
        'dist',
        '*.egg-info',
        '**/__pycache__',
        '**/*.pyc',
        '**/*.pyo',
        '.pytest_cache',
        '.coverage',
    ]
    
    for pattern in patterns:
        if '*' in pattern:
            import glob
            for path in glob.glob(str(ROOT_DIR / pattern), recursive=True):
                path_obj = Path(path)
                if path_obj.is_dir():
                    shutil.rmtree(path_obj)
                    print_success(f"删除 {path_obj.relative_to(ROOT_DIR)}/")
                elif path_obj.is_file():
                    path_obj.unlink()
                    print_success(f"删除 {path_obj.relative_to(ROOT_DIR)}")
        else:
            path = ROOT_DIR / pattern
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                    print_success(f"删除 {pattern}/")
                else:
                    path.unlink()
                    print_success(f"删除 {pattern}")
    
    print_success("清理完成")

def test():
    """运行测试"""
    print_header("运行测试")
    
    tests = [
        ("导入主模块", "import AutoCom; print('OK')"),
        ("导入版本", "import version; print(version.__version__)"),
        ("导入组件", "from components import CommandDeviceDict, CommandExecutor, DataStore, Device; print('OK')"),
        ("导入工具", "from utils import CommonUtils, ActionHandler, CustomActionHandler; print('OK')"),
        ("CLI模块", "import cli; print('OK')"),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_code in tests:
        result = run_command(f'python -c "{test_code}"', check=False, capture=True)
        if result:
            print_success(f"{test_name}: {result}")
            passed += 1
        else:
            print_error(f"{test_name}: 失败")
            failed += 1
    
    print(f"\n总计: {passed}/{len(tests)} 测试通过")
    
    # 测试 CLI 命令
    print("\n检查 CLI 命令...")
    # 尝试直接调用
    result = subprocess.run(["autocom", "-v"], capture_output=True, text=True, cwd=ROOT_DIR)
    if result.returncode == 0 and result.stdout:
        print_success(f"autocom 命令: {result.stdout.strip()}")
    else:
        # 尝试通过 python -m 调用
        result2 = subprocess.run(["python", "-m", "cli", "-v"], capture_output=True, text=True, cwd=ROOT_DIR)
        if result2.returncode == 0:
            print_success(f"CLI 模块: {result2.stdout.strip()}")
        else:
            print_warning("autocom 命令未安装 (运行 'python scripts/dev.py install' 安装)")
    
    return failed == 0

def build():
    """构建分发包"""
    print_header("构建分发包")
    
    # 确保安装了 build
    print_info("检查构建工具...")
    try:
        import build as _
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
            print("\nPackages:")
            for file in dist_dir.iterdir():
                size = file.stat().st_size / 1024
                print(f"   - {file.name} ({size:.1f} KB)")
        return True
    else:
        print_error("构建失败")
        return False

def install():
    """开发模式安装"""
    print_header("开发模式安装")
    
    print_info("以开发模式安装 AutoCom...")
    if run_command(f'"{sys.executable}" -m pip install -e .'):
        print_success("安装成功!")
        
        # 验证安装
        result = test()
        if result:
            print_success("安装验证通过")
        else:
            print_error("安装验证失败")
    else:
        print_error("安装失败")
        return False

def version(new_version=None):
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
    if not re.match(r'^\d+\.\d+\.\d+$', new_version):
        print_error(f"版本号格式不正确: {new_version}")
        print_info("正确格式: x.y.z (使用点号分隔,例如: 1.0.1, 1.2.3)")
        
        # 检测常见错误
        if ',' in new_version:
            print_warning(f"检测到逗号,应该使用点号: {new_version.replace(',', '.')}")
        
        return False
    
    # 确认更新
    print(f"\n{Colors.YELLOW}将版本从 {current} 更新到 {new_version}{Colors.END}")
    response = input("确认? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print_warning("已取消")
        return False
    
    # 更新版本
    if set_version(new_version):
        print_success(f"版本已更新: {current} -> {new_version}")
        
        print("\nNext steps:")
        print("  1. git add version.py")
        print(f"  2. git commit -m \"Bump version to v{new_version}\"")
        print(f"  3. git tag v{new_version}")
        print(f"  4. git push && git push origin v{new_version}")
        return True
    else:
        print_error("版本更新失败")
        return False

def publish():
    """发布到 PyPI"""
    print_header("发布到 PyPI")
    
    # 检查 twine
    print_info("检查发布工具...")
    try:
        import twine as _
    except ImportError:
        print_warning("未安装 twine,正在安装...")
        run_command(f'"{sys.executable}" -m pip install twine')
    
    # 检查 dist 目录
    dist_dir = ROOT_DIR / "dist"
    if not dist_dir.exists() or not list(dist_dir.iterdir()):
        print_error("没有找到构建产物")
        print_info("请先运行: python dev.py build")
        return False
    
    # 列出文件
    print("\nFiles to publish:")
    for file in dist_dir.iterdir():
        print(f"   - {file.name}")
    
    # 确认
    print(f"\n{Colors.YELLOW}准备发布到 PyPI{Colors.END}")
    response = input("确认? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print_warning("已取消")
        return False
    
    # 上传
    print_info("上传到 PyPI...")
    if run_command(f'"{sys.executable}" -m twine upload dist/* --disable-progress-bar'):
        print_success("发布成功!")
        
        current = get_current_version()
        if current:
            print(f"\nAutoCom v{current} published to PyPI!")
            print(f"   Users can install via:")
            print(f"   pip install autocom=={current}")
        return True
    else:
        print_error("发布失败")
        return False

def help_text():
    """显示帮助信息"""
    print_header("AutoCom 开发工具")
    
    print("用法: python dev.py [命令] [参数]")
    print("\n可用命令:")
    print("  clean              清理构建产物")
    print("  test               运行测试")
    print("  build              构建分发包")
    print("  install            开发模式安装")
    print("  version [x.y.z]    查看或更新版本")
    print("  publish            发布到 PyPI")
    print("  help               显示此帮助信息")
    
    print("\n常用工作流:")
    print("  1. 开发:")
    print("     python dev.py install    # 开发模式安装")
    print("     python dev.py test       # 运行测试")
    
    print("\n  2. 发布新版本:")
    print("     python dev.py version 1.1.0    # 更新版本号")
    print("     python dev.py test             # 测试")
    print("     python dev.py build            # 构建")
    print("     python dev.py publish          # 发布到 PyPI")
    
    print("\n  3. 本地测试安装:")
    print("     python dev.py build")
    print("     pip install --force-reinstall dist/autocom-*.whl")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        help_text()
        return 0
    
    command = sys.argv[1].lower()
    
    commands = {
        'clean': clean,
        'test': test,
        'build': build,
        'install': install,
        'publish': publish,
        'help': help_text,
    }
    
    if command == 'version':
        new_ver = sys.argv[2] if len(sys.argv) > 2 else None
        return 0 if version(new_ver) else 1
    elif command in commands:
        result = commands[command]()
        return 0 if result or result is None else 1
    else:
        print_error(f"未知命令: {command}")
        help_text()
        return 1

if __name__ == '__main__':
    sys.exit(main())
