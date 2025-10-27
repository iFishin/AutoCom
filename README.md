<div align="center">

# AutoCom

*一款用于自动化执行串口指令的脚本,支持多设备、多指令的串行和并行执行。*

![Cross Platform](https://img.shields.io/badge/cross--platform-Windows%20%26%20Linux-success.svg)
![Serial Communication](https://img.shields.io/badge/communication-Serial%20Port-orange.svg)
![Multi-Device](https://img.shields.io/badge/support-Multi--Device-blueviolet.svg)
![Automation](https://img.shields.io/badge/type-Automation%20Tool-red.svg)
![PyPI](https://img.shields.io/badge/PyPI-autocom-blue.svg)

</div>

---

## 📁 项目结构

```
AutoCom/
├── 📂 components/          # 核心组件模块
│   ├── CommandDeviceDict.py
│   ├── CommandExecutor.py
│   ├── DataStore.py
│   └── Device.py
├── 📂 utils/              # 工具类和辅助函数
│   ├── ActionHandler.py
│   ├── CommonUtils.py
│   └── custom_actions.py
├── 📂 scripts/            # 构建和维护脚本
│   ├── prepare_package.py    # 打包前准备脚本
│   ├── test_package.py       # 包测试脚本
│   └── update_version.py     # 版本更新脚本
├── 📂 docs/               # 项目文档
│   ├── About.md              # 项目详细介绍
│   └── AutoCom字典使用示例.md # 字典配置示例
├── 📂 dicts/              # 字典配置文件目录 (用户创建)
├── 📂 configs/            # 设备配置文件目录 (用户创建)
├── 📂 temps/              # 临时数据存储目录 (自动生成)
├── 📂 device_logs/        # 设备日志目录 (自动生成)
├── AutoCom.py             # 主程序入口
├── cli.py                 # 命令行接口
├── version.py             # 版本信息
├── __init__.py            # 包初始化文件
└── README.md              # 项目说明文档
```

### 📂 目录说明

- **components/** - 核心功能组件,包含设备管理、指令执行、数据存储等核心模块
- **utils/** - 工具函数和操作处理器,包含自定义 Action 扩展接口
- **scripts/** - 开发和维护脚本
  - `prepare_package.py` - 打包前准备,同步源代码到 autocom/ 目录
  - `test_package.py` - 测试包安装和功能
  - `update_version.py` - 自动更新版本号和版本历史
- **docs/** - 项目文档
  - `About.md` - 项目详细说明和设计文档
  - `AutoCom字典使用示例.md` - 字典配置文件使用示例和最佳实践
- **dicts/** - 存放指令字典配置文件 (需要使用 `autocom --init` 初始化创建)
- **configs/** - 存放设备配置模板文件 (需要使用 `autocom --init` 初始化创建)
- **temps/** - 临时数据存储,运行时自动创建
- **device_logs/** - 设备执行日志,运行时自动创建

> 💡 **提示**: 首次使用前,运行 `autocom --init` 初始化项目结构并生成示例配置文件。

---

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install autocom
```

### 从 GitHub 直接安装

无需等待 PyPI 发布,可以直接从 GitHub 安装最新版本:

```bash
# 从 main 分支安装最新版本
pip install git+https://github.com/iFishin/AutoCom.git

# 从特定版本安装 (推荐)
pip install git+https://github.com/iFishin/AutoCom.git@v1.0.0
```

> 💡 更多安装方式请查看 [INSTALL.md](INSTALL.md)

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/iFishin/AutoCom.git
cd AutoCom

# 安装依赖
pip install -r requirements.txt

# 开发模式安装（可编辑）
pip install -e .
```

### 手动打包安装

如果你想自己打包:

```bash
# 1. 准备包结构
python scripts/prepare_package.py

# 2. 构建包
python -m build

# 3. 安装
pip install dist/autocom-1.0.0-py3-none-any.whl
```

详细打包说明请查看 [docs/PACKAGING.md](docs/PACKAGING.md)

---

## 📦 打包和发布

### 打包前准备

1. **安装打包工具**

```bash
pip install build twine
```

2. **准备包结构**

运行准备脚本,将源代码复制到 `autocom/` 目录:

```bash
python scripts/prepare_package.py
```

### 构建发行包

使用 `build` 工具构建源码包（.tar.gz）和 wheel 包（.whl）：

```bash
python -m build
```

构建成功后，会在 `dist/` 目录生成两个文件：
- `autocom-1.0.0-py3-none-any.whl` - wheel 包（推荐安装方式）
- `autocom-1.0.0.tar.gz` - 源码包

### 本地测试安装

创建虚拟环境测试包安装：

```bash
# 创建测试虚拟环境
python -m venv test_venv

# Windows 激活虚拟环境
.\test_venv\Scripts\Activate.ps1

# Linux/Mac 激活虚拟环境
source test_venv/bin/activate

# 安装 wheel 包
pip install dist/autocom-1.0.0-py3-none-any.whl

# 测试安装
autocom -v
python -c "import autocom; print(autocom.__version__)"

# 退出虚拟环境
deactivate
```

### 发布到 PyPI

#### 1. 注册 PyPI 账号

在 [PyPI](https://pypi.org/account/register/) 注册账号

#### 2. 配置 API Token

在 PyPI 账号设置中生成 API Token，然后配置到本地：

```bash
# 创建 .pypirc 文件（Linux/Mac 在 ~/.pypirc，Windows 在 %USERPROFILE%\.pypirc）
# 内容如下：
[pypi]
username = __token__
password = pypi-AgEIcHlwaS5vcmc...（你的 API Token）
```

#### 3. 上传到 PyPI

```bash
# 上传到 PyPI
twine upload dist/*

# 或者先上传到 TestPyPI 测试
twine upload --repository testpypi dist/*
```

#### 4. 验证发布

```bash
# 从 PyPI 安装
pip install autocom

# 测试
autocom -v
```

### 版本更新流程

当需要发布新版本时：

1. **更新版本号**

使用 `scripts/update_version.py` 脚本更新版本:

```bash
# 语法: python scripts/update_version.py <新版本号> "<更新说明>"
python scripts/update_version.py 1.1.0 "添加新功能: XXX"
```

这个脚本会:
- 更新 `version.py` 中的版本号
- 更新 `AutoCom.py` 中的版本号
- 在 `VERSION_HISTORY` 中添加更新日志
- 自动验证版本号格式(语义化版本)

2. **测试新版本**

```bash
# 运行测试
python scripts/test_package.py

# 查看版本
python AutoCom.py -v
```

3. **提交代码**

```bash
git add .
git commit -m "Release v1.1.0: 添加新功能"
git tag v1.1.0
git push origin main --tags
```

4. **构建并发布**

```bash
# 清理旧的构建文件
rm -rf dist/ build/ *.egg-info

# 重新构建
python scripts/prepare_package.py
python -m build

# 上传到 PyPI
twine upload dist/*
```

### 版本号规范

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范：

- **主版本号（Major）**：不兼容的 API 修改
- **次版本号（Minor）**：向下兼容的功能性新增
- **修订号（Patch）**：向下兼容的问题修正

示例：`1.2.3` 表示主版本1，次版本2，修订号3

### 自动化脚本

项目提供了几个辅助脚本(位于 `scripts/` 目录):

- `prepare_package.py` - 准备包结构
- `update_version.py` - 更新版本号
- `test_package.py` - 测试包安装

详细文档(位于 `docs/` 目录):
- [About.md](docs/About.md) - 项目详细介绍
- [AutoCom字典使用示例.md](docs/AutoCom字典使用示例.md) - 字典配置示例

---

## 🚀 快速开始

### 命令行使用

安装后，可以直接使用 `autocom` 命令：

```bash
# 执行字典文件（循环3次）
autocom -d dicts/dict.json -l 3

# 无限循环模式（按 Ctrl+C 停止）
autocom -d dicts/dict.json -i

# 使用配置文件
autocom -d dicts/dict.json -c configs/FCM100D.json

# 执行文件夹内所有字典文件
autocom -f dicts/

# 监控模式（监听文件夹，自动执行新文件）
autocom -m temps/
```

### Python API 使用

```python
from autocom import CommandDeviceDict, CommandExecutor, CommonUtils

# 加载配置
dict_data = {...}  # 你的配置字典
device_dict = CommandDeviceDict(dict_data)

# 创建执行器
executor = CommandExecutor(device_dict)

# 执行指令
result = executor.execute()

# 清理资源
device_dict.close_all_devices()
executor.data_store.stop()
```

---
## 📑 目录

- [AutoCom](#autocom)
  - [📁 项目结构](#-项目结构)
    - [📂 目录说明](#-目录说明)
  - [安装](#安装)
    - [从 PyPI 安装（推荐）](#从-pypi-安装推荐)
    - [从 GitHub 直接安装](#从-github-直接安装)
    - [从源码安装](#从源码安装)
    - [手动打包安装](#手动打包安装)
  - [📦 打包和发布](#-打包和发布)
    - [打包前准备](#打包前准备)
    - [构建发行包](#构建发行包)
    - [本地测试安装](#本地测试安装)
    - [发布到 PyPI](#发布到-pypi)
      - [1. 注册 PyPI 账号](#1-注册-pypi-账号)
      - [2. 配置 API Token](#2-配置-api-token)
      - [3. 上传到 PyPI](#3-上传到-pypi)
      - [4. 验证发布](#4-验证发布)
    - [版本更新流程](#版本更新流程)
    - [版本号规范](#版本号规范)
    - [自动化脚本](#自动化脚本)
  - [🚀 快速开始](#-快速开始)
    - [命令行使用](#命令行使用)
    - [Python API 使用](#python-api-使用)
  - [📑 目录](#-目录)
- [AutoCom Feature Checklist](#autocom-feature-checklist)
  - [执行方式](#执行方式)
  - [格式框架](#格式框架)
    - [设备](#设备)
      - [设备参数](#设备参数)
      - [设备列表全局配置](#设备列表全局配置)
    - [操作项](#操作项)
      - [操作项参数](#操作项参数)
      - [操作项全局配置](#操作项全局配置)
      - [操作项编写指南](#操作项编写指南)
    - [指令](#指令)
      - [指令参数](#指令参数)
      - [指令列表全局配置](#指令列表全局配置)
    - [临时性数据](#临时性数据)
  - [使用示例](#使用示例)

---

# AutoCom Feature Checklist

- [x] 指定某条指令状态改为可用，指定都是用序号来选取，如果有同号则只对第一个进行操作
- [x] 指定执行某条指令，指定都是用序号来选取，如果有同号则只对第一个进行操作
- [x] 是否加入对特定成功or错误执行特定操作？
- [x] 是否加入自定义指令执行的action？
- [x] 是否加入全局success or error actions操作？
- [x] 加入脚本判断日志？方便调试和分析执行日志
- [x] 加入持续监听，首先加入Devices的全局配置块，在全局配置块种指定持续监听的设备
- [ ] 全局成功/错误响应actions要指定设备监听
- [x] 对于status为disabled的设备，相应的指令也置为disabled
- [x] 增加字符替换action
- [x] 是否加入对文件夹内所有执行字典遍历的操作，加入控制字符`-f`,文件夹内是怎样个执行顺序？
- [x] 是否加入一轮结束后，对该轮的执行情况标注通过与否？
- [x] 优化持续监听逻辑
- [x] 加入配置控制字符`-c`,用于使用指定配置模板，配置文件使用覆盖逻辑
- [x] 文件夹遍历字典取消重复打开串口的逻辑
- [ ] 某些情况下，卡在时间点，会在device_logs创建两个日志文件夹
- [x] 日志打印乱码，进行强制编码输出到日志文本
- [x] 使用`monitor`大量数据会出现吞log的情况，是否加入数据分割？
- [ ] 指令超时判断的逻辑，是否需要设计成捕获完预期结果后，提前结束？
- [ ] 针对不含`command`或者`expected_responses`的指令，放行策略？
- [x] 是否要剥离actions的函数，把他单独设计成一个扩展的类？
- [x] 加入对指定文件夹的监听逻辑，当文件夹内有新文件时，自动执行该文件内的指令，执行完毕后删除该文件
- [ ] 启用`dependencies`指令属性，逻辑为：依赖指令列表中的所有指令执行通过后，才执行本条指令，如果含失败项则跳过执行。这个跳过状态定义为失败可行？后执行失败操作？
- [ ] 成功/失败响应actions是否统一成一个就行了？
- [x] 自定义ActionHandler的开发接口说明
- [ ] 主线程阻塞过久，卡死？
- [x] 加入Linux系统执行适配
- [ ] 新剥离的ActionHandler无法正确传递执行成功与否
- [ ] 对于不含串口执行的子项需要优化
- [x] 对脚本内各个功能进行组件拆分，方便后续维护
- [x] 在Linux中串口号带路径分隔符，是否需要进行适配？
- [ ] 多个设备开启monitor监听会有问题，需要优化，需要重写逻辑，开启monitor的设备收发和判断逻辑需要完善
- [ ] 需要加入指定结束符，考虑放在Device配置中去？
- [ ] 检查执行Actions中含重新执行指令项的逻辑，重试指令项不需要执行Action的内容
- [ ] 针对空command字段，即只是获取响应数据的子项，也需要加上个分隔符号作区分
- [ ] 单独出来一个初始化常量的配置块
- [ ] 还是得使用全局串口，保证持续监听
- [ ] 表格打印用三方插件来做

---

## 执行方式

- **单个字典文件执行**

`python AutoCom.py -d <xxx.json> -l <times> [-c <configFile>]`

- **文件夹内所有字典文件顺序执行**

`python AutoCom.py -f <dictFilePath> -c <configFile>`

> 文件夹内的文件命名得加上前缀区分执行顺序：`[<order>]<filename>.json`
> 

- **监听文件夹内新文件**

`python -m <monitoredFilePath>`

## 格式框架

### 设备

<details> 
<summary><font size="6">Devices</font></summary> 
<pre><code class="json">
"Devices": [
        {
            "name": "DeviceA",
            "status": "enabled",
            "port": "COM65",
            "baud_rate": 115200,
            "stop_bits": 1,
            "parity": null,
            "data_bits": 8,
            "flow_control": {
                "xon_xoff": false,
                "rts_cts": false,
                "dsr_dtr": false
            },
            "dtr": false,
            "rts": false
        },
        {
            "name": "DeviceB",
            "status": "disabled",
            "port": "COM64",
            "baud_rate": 115200,
            "stop_bits": 1,
            "parity": null,
            "data_bits": 8,
            "flow_control": {
                "xon_xoff": false,
                "rts_cts": false,
                "dsr_dtr": false
            },
            "dtr": false,
            "rts": false
        }
    ]
</code>
</pre></details>

#### 设备参数

| Device    | 内容                                | 作用                 |
| --------- | ----------------------------------- | -------------------- |
| name      | 设备名称（如 "DeviceA"、"DeviceB"） | 标识不同的设备       |
| status    | 设备状态（"enabled"/"disabled"）    | 表示设备当前状态     |
| port      | 串口名称（如 "COM65"）              | 指定设备物理连接端口 |
| baud_rate | 波特率（如 115200）                 | 设定通信速率         |
| stop_bits | 停止位（1/2）                       | 设定停止位           |
| parity    | 奇偶校验（"None"/"Even"/"Odd"）     | 设定奇偶校验         |
| data_bits | 数据位（5/6/7/8）                   | 设定数据位           |
| flow_control | 流控制配置                        | 设定流控制           |
| dtr       | DTR信号（true/false）               | 设定DTR信号          |
| rts       | RTS信号（true/false）               | 设定RTS信号          |
| <u>monitor</u> | 是否持续监听设备（true/false）          | 设定是否持续监听日志 |

> 配置执行设备的基本信息。
>
> monitor是针对Debug串口设计的持续日志监听功能，当该属性开启之后，会单独启动一个线程持续监听来自串口的日志。默认情况下是关闭，默认的监听逻辑为**有指令发送至该串口后，才会监听一次来自串口的返回数据。**

#### 设备列表全局配置

> 更新加入了`ConfigForDevices`属性块，可以利用全局配置来减少设备列表的属性编辑
>
> 覆盖逻辑为：**`ConfigForDevices`中的键值对只会替换`Devices`中相对应不存在的键值对**，相反的，如果`Devices`中存在`status: "enabled"`，且你在`ConfigForDevices`中也设置了该属性，则不会利用全局配置来替换。

<details> 
<summary><font size="6">With ConfigForDevices</font></summary> 
<pre><code class="language-json">
 "ConfigForDevices": {
        "status": "enabled",
        "stop_bits": 1,
        "parity": null,
        "data_bits": 8,
        "flow_control": {
            "xon_xoff": false,
            "rts_cts": false,
            "dsr_dtr": false
        },
        "dtr": false,
        "rts": false
    },
    "Devices": [
        {
            "name": "DeviceA",
            "port": "COM14",
            "baud_rate": 115200
        },
        {
            "name": "DebugA",
            "port": "COM13",
            "baud_rate": 115200,
            "monitor": true
        },
        {
            "name": "DeviceB",
            "port": "COM36",
            "baud_rate": 115200
        }
    ]
</code>
</pre> </details>

### 操作项

新版中，已剥离了Actions操作项的函数，单独设计成一个扩展的类，Actions类中包含了所有操作项的实现逻辑。用户可以根据自己的需求，自定义操作项的实现逻辑，方便扩展和维护。

#### 操作项参数

| actions                  | 格式                                                         | 说明                     |
| ------------------------ | ------------------------------------------------------------ | ------------------------ |
| retry                    | {"retry": 3}                                                 | 重试指令执行次数，会执行success_actions |
| save                     | {"save": {"device": "DeviceA", "variable": "version_info", "value": "HCM511S"}} | 保存数据                 |
| save_conditional         | {"save_conditional": {"device": "DeviceA","pattern": "\\+QVERSION: (.+)", "variable": "version_info"}} | 保存指令指定响应结果     |
| wait                     | { "wait": {"duration": wait_time_in_milliseconds} }                                                 | 等待指定时间, 单位为毫秒   |
| set_status               | {"set_status": "enabled"} OR {"set_status": "disabled"}      | 设置指令状态             |
| print                    | {"print": "Hello World"}                                     | 打印指定内容             |
| set_status_by_order      | {"set_status_by_order": {"order": 2, "status": "enabled" } } | 设置指定指令状态         |
| execute_command          | {"execute_command": 3}                                       | 忽略status，执行指定指令 |
| execute_command_by_order | { "execute_command_by_order": 3 }                            | 忽略status，执行指定指令 |
| generate_random_str      | { "generate_random_str": { "device": "DeviceA", "length": 100, "variable": "random_data" } } | 生成指定长度随机字符串           |
| calculate_length | { "calculate_length": { "data": "{random_data}", "device": "DeviceA", "variable": "random_data_length" } } | 计算字符串长度           |
| replace_str | { "replace_str": { "device": "DeviceA", "data": "{ble_address}", "original_str": ":", "new_str": "" } } | 字符串替换，这里的device为存入的目标设备 |

> actions也是一个list类型，包含了针对特定情境的处理方式，如果指令包含了相应的actions项，则会顺序执行列表内的所有action项。

#### 操作项全局配置

> 更新加入了`ConfigForActions`属性块，可以引入自定义的操作项配置。

<details>
<summary><font size="6">With ConfigForActions</font></summary>
<pre><code class="language-json">
{
  "ConfigForActions": {
    "handler_class": "utils.custom_actions.CustomActionHandler"
  },
  "Devices": [...],
  "Commands": [...]
}
</code>
</pre> </details>

#### 操作项编写指南

在分离ActionHandler之后，在`utils/ActionHandler`中编写了常用到的action操作，下面用一个简单的例子来讲解自定义Action编写方法：

~~~python
def handle_test(self, text, command, response, context):
    """
    测试功能

    用法:
    {
        "test": "test_message"
    }
    """
    test_message = self.handle_variables_from_str(text)
    CommonUtils.print_log_line(f"ℹ Test action executed with message: {test_message}")
    CommonUtils.print_log_line("")
    return True
~~~

首先先了解这个Action是指的什么。上面注释中所描述的`{ "test": "test_message" }`是一个Action项，也是一个Object对象，这个Action项的名称为`test`，而这个Action的内容则是`test_message`。在执行时，这个Action会被传入到`handle_test`函数中。
然后看看传入的参数列表：

① `self`这个是指向当前ActionHandler实例的引用，这里必须包含，用于注册ActionHandler的函数
② `text`这个是传入action所含的Object内容，这里是指`{"test": "test_message"}`中的`"test_message"`部分。如果action名包含的是一个Object对象，则会将该对象传入，这里需要注意类型对应。
③ `command`这个是指当前执行的指令对象，也就是指令字典中的`command`属性内容。
④ `response`这个是指当前指令执行后响应内容，<u>这个类型是`List`</u>,得注意。
⑤ `context`这个是指当前执行上下文，包含了当前设备、指令等信息。这里的context内容目前为：

~~~json
{
        "device": device,
        "device_name": device_name,
        "cmd_str": cmd_str,
        "expected_responses": updated_expected_responses
}
~~~

> 由于ActionHandler扩展性太多，后续可能变更，请以实际代码逻辑为准。


### 指令

<details> 
<summary><font size="6">Commands</font></summary> 
<pre><code class="language-json">
"Commmands": [		
        {
            "command": "AT+QRST",
            "status": "enabled",
            "expected_responses": [
                "OK",
                "RDY"
            ],
            "device": "DeviceA",
            "order": 1,
            "parameters": [],
            "timeout": 2000,
            "concurrent_strategy": "parallel",
            "success_actions": [
                {
                    "set_status": "disabled"
                }
            ],
            "success_response_actions": [
            ],
            "error_actions": [
                {
                    "retry": 3
                }
            ],
            "error_response_actions": [
            ]
        },
        {
            "command": "AT+QSTAAPINFO=\"TestForFish\",\"12345678\"",
            "status": "enabled",
            "expected_responses": [
                "OK"
            ],
            "device": "DeviceA",
            "order": 3,
            "parameters": [],
            "timeout": 3000,
            "concurrent_strategy": "sequential",
            "success_actions": [
                {
                    "set_status": "disabled"
                }
            ],
            "success_response_actions": {
                "GOT_IP": [
                    {
                        "print": "GOT_IP"
                    }
                ]
            },
            "error_actions": [
                {
                    "retry": 3
                }
            ],
            "error_response_actions": {
                "WLAN_DISCONNECTED": [
                    {
                        "print": "DISCONNECTED"
                    }
                ],
                "SCAN_NO_AP": [
                    {
                        "print": "NO AP"
                    }
                ]
            }
        }
    ]
</code>
</pre> </details>

#### 指令参数

| Command                   | 内容                             | 作用                 |
| ------------------------- | -------------------------------- | -------------------- |
| <u>command</u>            | AT指令字符串（如 "AT+QRST"）     | 发送给设备的具体指令 |
| status                    | 指令状态（"enabled"/"disabled"） | 指定指令是否可用     |
| <u>expected_responses</u> | 预期响应列表（如 ["OK","RDY"]）  | 判断指令执行成功条件 |
| device                    | 目标设备名称                     | 指定执行指令的设备   |
| order                     | 执行顺序（整数）                 | 确定指令执行顺序     |
| <u>parameters</u>         | 指令参数列表                     | 提供指令所需参数     |
| timeout                   | 超时时间（毫秒）                 | 设定指令执行时限     |
| concurrent_strategy       | "sequential"或"parallel"         | 设定指令并发策略     |
| **error_actions**         | 错误处理配置                     | 定义错误响应处理方式 |
| **success_actions**       | 成功后续操作                     | 指定成功后的附加动作 |
| **error_response_actions** | 错误响应后续操作                 | 特定错误响应后的动作 |
| **success_response_actions** | 成功响应后续操作                 | 特定成功响应后的动作 |
| ~~dependencies~~          | 依赖指令列表                     | 设定指令执行依赖项   |

> - command
> - expected_responses
> - parameters
>
> expected_responses 的判断逻辑为：顺序匹配，只有所有预期响应都匹配成功，才认为指令执行成功
>
> 上面参数都支持向临时数据文件中取用变量，取用逻辑为：`{variable_name}`
>
> ---
>
> - variable_name
>
> 这个变量的命名格式是字母和下划线的混合
>
> 如果临时数据文件中存在该变量则返回对应的值
>
> 如果临时数据文件中不存在该变量，则会原始文本输出{variable_name}
>
> ---
>
> - concurrent_strategy
>
> 脚本中的并发策略为：为相邻参与并行执行的指令按照设备分组，然后为每个设备创建一个线程，并行执行完成后返回直接结果，线程设置了30ms超时时限，防止阻塞。
>
> ---
>
> - order
>
> 这个执行序号如若遇到序号相同的情形，指令重排之后，相同序号的指令则会按照原始排列出现的顺序执行


#### 指令列表全局配置

> 覆盖逻辑同`ConfigForDevices`,用于简化重复的属性配置。

<details> 
<summary><font size="6">With ConfigForDevices</font></summary> 
<pre><code class="language-json">
    "ConfigForCommands": {
        "status": "enabled",
        "timeout": 1000,
        "concurrent_strategy": "sequential",
        "error_actions": [
            {
                "retry": 1
            }
        ]
    },
    "Commands": [
        {
            "command": "AT+QRST",
            "expected_responses": [
                "OK",
                "RDY"
            ],
            "device": "DeviceA",
            "success_actions": [
                {
                    "set_status": "disabled"
                }
            ],
            "order": 1
        },
        {
            "command": "AT+QECHO=1",
            "expected_responses": [
                "OK"
            ],
            "device": "DeviceA",
            "success_actions": [
                {
                    "set_status": "disabled"
                }
            ],
            "order": 1
        },
        {
            "command": "AT+QRST",
            "expected_responses": [
                "OK",
                "RDY"
            ],
            "device": "DeviceB",
            "success_actions": [
                {
                    "set_status": "disabled"
                }
            ],
            "order": 1
        },
        {
            "command": "AT+QECHO=1",
            "expected_responses": [
                "OK"
            ],
            "device": "DeviceB",
            "success_actions": [
                {
                    "set_status": "disabled"
                }
            ],
            "order": 1
        }
    ]
</code>
</pre> </details>

### 临时性数据

<details> 
<summary><font size="6">Temp-Data</font></summary> 
<pre><code class="language-json">
{
  "DeviceB": {
    "fish": "RST",
    "gatt_char": "\"36f5\"",
    "ble_address": "\"D87A3B6D522B\""
  },
  "DeviceA": {
    "gatt_char": "\"36f5\""
  }
}
</code>
</pre> </details>
> Temp-Data可当作一个简易数据库的功能，用于存取执行过程中的各类临时性变量。

目前这个数据存取使用一个`DataStore`类来控制，该类目前提供了两个方法：

- **store_data**

> 用于存储变量到指定设备名中去。操作方法为（data_store为实例）：
>
> `data_store.store_data(<device_name>, <variable_name>, <value>)`

- **get_data**

> 用于获取指定设备名中的变量值。操作方法为（data_store为实例）：
>
> `data_store.get_data(<device_name>, <variable_name>)`

## 使用示例

参看示例：
[AutoCom字典使用示例](AutoCom字典使用示例.md)

