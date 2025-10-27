#!/usr/bin/env python
"""
版本更新脚本

用于更新 AutoCom 的版本号。只需修改 autocom/version.py，
其他所有地方都会自动从该文件读取版本。

用法:
    python update_version.py 1.1.0
    python update_version.py 1.1.0 "新增功能描述"
"""
import sys
import os
import re
from datetime import datetime

def update_version_file(new_version, changelog_message=None):
    """更新 version.py 文件中的版本号和变更日志"""
    version_file = os.path.join('autocom', 'version.py')
    
    if not os.path.exists(version_file):
        print(f"❌ 错误: 找不到 {version_file}")
        return False
    
    # 读取当前内容
    with open(version_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 获取当前版本
    current_version_match = re.search(r'__version__ = ["\']([^"\']+)["\']', content)
    if current_version_match:
        current_version = current_version_match.group(1)
        print(f"📌 当前版本: {current_version}")
    else:
        current_version = "未知"
    
    # 更新版本号
    content = re.sub(
        r'__version__ = ["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        content
    )
    
    # 如果提供了变更日志消息，更新 VERSION_HISTORY
    if changelog_message:
        today = datetime.now().strftime('%Y-%m-%d')
        new_changelog = f"""
v{new_version} ({today})
  - {changelog_message}
"""
        
        # 在 VERSION_HISTORY 中添加新版本
        content = re.sub(
            r'(VERSION_HISTORY = """)',
            f'\\1{new_changelog}',
            content
        )
    
    # 写回文件
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 版本已更新: {current_version} -> {new_version}")
    if changelog_message:
        print(f"📝 变更日志: {changelog_message}")
    
    return True

def update_autocom_py(new_version):
    """更新 AutoCom.py 中的版本号"""
    autocom_file = 'AutoCom.py'
    
    if not os.path.exists(autocom_file):
        print(f"⚠️  警告: 找不到 {autocom_file}")
        return False
    
    with open(autocom_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 更新版本号
    content = re.sub(
        r'__version__ = ["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        content
    )
    
    with open(autocom_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 已更新 {autocom_file}")
    return True

def verify_version(version_string):
    """验证版本号格式是否正确 (x.y.z)"""
    pattern = r'^\d+\.\d+\.\d+$'
    if not re.match(pattern, version_string):
        print(f"❌ 错误: 版本号格式不正确: {version_string}")
        print("   正确格式应该是: x.y.z (例如: 1.0.0, 1.2.3)")
        return False
    return True

def show_current_version():
    """显示当前版本"""
    version_file = os.path.join('autocom', 'version.py')
    
    if not os.path.exists(version_file):
        print(f"❌ 错误: 找不到 {version_file}")
        return
    
    with open(version_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    version_match = re.search(r'__version__ = ["\']([^"\']+)["\']', content)
    if version_match:
        version = version_match.group(1)
        print(f"📦 当前版本: {version}")
    else:
        print("❌ 无法读取版本号")

def main():
    """主函数"""
    print("=" * 60)
    print("AutoCom 版本更新工具")
    print("=" * 60)
    print()
    
    # 显示当前版本
    show_current_version()
    print()
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python update_version.py <新版本号>")
        print("  python update_version.py <新版本号> <变更说明>")
        print()
        print("示例:")
        print("  python update_version.py 1.1.0")
        print('  python update_version.py 1.1.0 "新增 -v 参数查看版本"')
        print()
        return 1
    
    new_version = sys.argv[1]
    changelog_message = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 验证版本号格式
    if not verify_version(new_version):
        return 1
    
    print(f"🎯 目标版本: {new_version}")
    if changelog_message:
        print(f"📝 变更说明: {changelog_message}")
    print()
    
    # 确认
    response = input("确认更新版本? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print("❌ 已取消")
        return 0
    
    print()
    print("开始更新...")
    print()
    
    # 更新 version.py (主要版本源)
    if not update_version_file(new_version, changelog_message):
        return 1
    
    # 更新 AutoCom.py (保持向后兼容)
    update_autocom_py(new_version)
    
    print()
    print("=" * 60)
    print("✨ 版本更新完成！")
    print("=" * 60)
    print()
    print("📝 后续步骤:")
    print("  1. 运行测试: python test_package.py")
    print("  2. 提交更改: git add . && git commit -m \"Bump version to v" + new_version + "\"")
    print("  3. 创建标签: git tag v" + new_version)
    print("  4. 重新构建: python -m build")
    print("  5. 发布新版: python -m twine upload dist/*")
    print()
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
