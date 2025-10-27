"""
测试 AutoCom 包是否正确安装和工作
"""

def test_import():
    """测试导入"""
    print("🧪 测试 1: 导入包...")
    try:
        import autocom
        print(f"   ✅ 成功导入 autocom 包")
        print(f"   📦 版本: {autocom.__version__}")
        print(f"   👤 作者: {autocom.__author__}")
    except ImportError as e:
        print(f"   ❌ 导入失败: {e}")
        return False
    return True

def test_components():
    """测试组件导入"""
    print("\n🧪 测试 2: 导入组件...")
    try:
        from autocom import CommandDeviceDict, CommandExecutor, DataStore, Device, CommonUtils
        print("   ✅ 成功导入所有组件")
        print(f"      - CommandDeviceDict")
        print(f"      - CommandExecutor")
        print(f"      - DataStore")
        print(f"      - Device")
        print(f"      - CommonUtils")
    except ImportError as e:
        print(f"   ❌ 组件导入失败: {e}")
        return False
    return True

def test_cli():
    """测试命令行工具"""
    print("\n🧪 测试 3: 检查命令行工具...")
    import subprocess
    try:
        result = subprocess.run(['autocom', '--help'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            print("   ✅ autocom 命令可用")
            return True
        else:
            print(f"   ⚠️  autocom 命令返回错误码: {result.returncode}")
            return False
    except FileNotFoundError:
        print("   ❌ autocom 命令未找到（可能需要重新安装）")
        return False
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False

def test_version():
    """测试版本信息"""
    print("\n🧪 测试 4: 检查版本信息...")
    try:
        import autocom
        version = autocom.__version__
        if version and len(version.split('.')) == 3:
            print(f"   ✅ 版本号格式正确: {version}")
            return True
        else:
            print(f"   ⚠️  版本号格式异常: {version}")
            return False
    except Exception as e:
        print(f"   ❌ 获取版本失败: {e}")
        return False

def main():
    """运行所有测试"""
    print("="*60)
    print("AutoCom 包测试")
    print("="*60)
    
    results = []
    results.append(("导入测试", test_import()))
    results.append(("组件测试", test_components()))
    results.append(("CLI测试", test_cli()))
    results.append(("版本测试", test_version()))
    
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！AutoCom 包工作正常。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查安装。")
        return 1

if __name__ == '__main__':
    exit(main())
