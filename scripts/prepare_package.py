"""
AutoCom 打包准备脚本

这个脚本会将项目文件组织成标准的 Python 包结构
注意: configs/dicts/dictFiles 等资源文件由 autocom --init 在用户工作目录创建,不打包到安装包中
"""
import os
import shutil

def copy_python_files(src_dir, dst_dir, desc):
    """复制目录中的 Python 文件"""
    # 确保目标目录存在
    os.makedirs(dst_dir, exist_ok=True)
    
    for file in os.listdir(src_dir):
        if file.endswith('.py') and file != '__init__.py':
            shutil.copy2(
                os.path.join(src_dir, file),
                os.path.join(dst_dir, file)
            )
            print(f"   ✅ {desc}/{file}")

def prepare_package():
    """准备打包结构"""
    print("📦 开始准备 AutoCom 包结构...")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    autocom_dir = os.path.join(base_dir, 'autocom')
    
    # 确保 autocom 目录存在
    os.makedirs(autocom_dir, exist_ok=True)
    
    # 1. 复制主程序文件
    print("\n1️⃣  复制主程序文件...")
    shutil.copy2(
        os.path.join(base_dir, 'AutoCom.py'),
        os.path.join(autocom_dir, 'AutoCom_main.py')
    )
    print("   ✅ AutoCom.py -> autocom/AutoCom_main.py")
    
    # 2. 复制包管理文件
    print("\n2️⃣  复制包管理文件...")
    for file in ['__init__.py', 'cli.py', 'version.py']:
        shutil.copy2(
            os.path.join(base_dir, file),
            os.path.join(autocom_dir, file)
        )
        print(f"   ✅ {file}")
    
    # 3. 复制 components 组件
    print("\n3️⃣  复制 components 组件...")
    copy_python_files(
        os.path.join(base_dir, 'components'),
        os.path.join(autocom_dir, 'components'),
        'components'
    )
    
    # 4. 复制 utils 工具
    print("\n4️⃣  复制 utils 工具...")
    copy_python_files(
        os.path.join(base_dir, 'utils'),
        os.path.join(autocom_dir, 'utils'),
        'utils'
    )
    
    print("\n✨ 包结构准备完成！")
    print("\n📝 后续步骤：")
    print("   1. 运行构建命令: python -m build")
    print("   2. 本地测试安装: pip install --force-reinstall dist/autocom-1.0.0-py3-none-any.whl")
    print("   3. 发布到 PyPI: python -m twine upload dist/*")

if __name__ == '__main__':
    prepare_package()
