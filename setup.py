from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read version from version.py
version = {}
with open(os.path.join(this_directory, 'version.py'), encoding='utf-8') as f:
    exec(f.read(), version)

setup(
    name="autocom",
    version=version['__version__'],
    author="iFishin",
    author_email="your.email@example.com",  # 请替换为你的邮箱
    description="一款用于自动化执行串口指令的脚本，支持多设备、多指令的串行和并行执行",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/iFishin/AutoCom",
    # 使用扁平结构,直接从根目录安装包
    packages=find_packages(exclude=['tests*', 'device_logs*', 'temps*', 'scripts*', 'res*', 'docs*', 'autocom*']),
    py_modules=['AutoCom', 'cli', 'version', '__init__'],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Testing",
        "Topic :: System :: Hardware :: Universal Serial Bus (USB) :: Human Interface Device (HID)",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Environment :: Console",
    ],
    python_requires=">=3.7",
    install_requires=[
        "pyserial>=3.5",
    ],
    entry_points={
        'console_scripts': [
            'autocom=cli:main',
        ],
    },
    include_package_data=True,
    keywords='serial automation testing embedded iot',
    project_urls={
        'Bug Reports': 'https://github.com/iFishin/AutoCom/issues',
        'Source': 'https://github.com/iFishin/AutoCom/',
    },
)
