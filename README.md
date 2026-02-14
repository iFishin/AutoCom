# AutoCom

*一款用于自动化执行串口指令的脚本,支持多设备、多指令的串行和并行执行。*

<div align="center">

![Cross Platform](https://img.shields.io/badge/cross--platform-Windows%20%26%20Linux-success.svg)
![Serial Communication](https://img.shields.io/badge/communication-Serial%20Port-orange.svg)
![Multi-Device](https://img.shields.io/badge/support-Multi--Device-blueviolet.svg)
![Automation](https://img.shields.io/badge/type-Automation%20Tool-red.svg)
![PyPI](https://img.shields.io/badge/PyPI-autocom-blue.svg)
</div>

---

## 📑 目录

- [AutoCom](#autocom)
  - [📑 目录](#-目录)
  - [📁 项目结构](#-项目结构)
    - [📂 目录说明](#-目录说明)
  - [安装](#安装)
    - [从 PyPI 安装（推荐）](#从-pypi-安装推荐)
    - [从 GitHub 直接安装](#从-github-直接安装)
    - [从源码安装](#从源码安装)
    - [手动打包安装](#手动打包安装)
  - [🚀 快速开始](#-快速开始)
    - [命令行使用](#命令行使用)
    - [Python API 使用](#python-api-使用)
  - [执行方式](#执行方式)
  - [格式框架](#格式框架)
    - [设备](#设备)
      - [设备参数](#设备参数)
      - [设备列表全局配置](#设备列表全局配置)
    - [操作项](#操作项)
      - [操作项全局配置](#操作项全局配置)
      - [操作项编写指南](#操作项编写指南)
    - [指令](#指令)
      - [指令参数](#指令参数)
      - [指令列表全局配置](#指令列表全局配置)
    - [临时性数据](#临时性数据)

## 📁 项目结构

```plain
AutoCom/
├── 📂 components/         # 核心组件模块
│   └── *.py
├── 📂 utils/              # 工具类和辅助函数
│   └── *.py
├── 📂 tests/              # 测试文件目录
│   └── *.py
├── 📂 scripts/            # 构建和维护脚本
│   └── *.py
├── 📂 docs/               # 项目文档
│   └── *.md
├── 📂 dicts/              # 字典配置文件目录
├── 📂 configs/            # 设备配置文件目录
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
  - `dev.py` - 统一开发工具,集成测试、构建、发布等功能
  - `update_actions_doc.py` - 更新 Actions.md 文档
- **docs/** - 项目文档
  - `Started.md` - 快速开始指南
  - `DEV.md` - 开发指南和工具说明
  - `About.md` - 项目详细说明和设计文档
  - `ToDO.md` - 待办事项和未来计划
  - `Actions.md` - 所有 Action 操作项的详细说明
- **dicts/** - 存放指令字典配置文件
- **configs/** - 存放设备配置模板文件
- **temps/** - 临时数据存储,运行时自动创建
- **device_logs/** - 设备执行日志,运行时自动创建

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
python scripts/dev.py build
pip install dist/autocom-<version>-py3-none-any.whl
```

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
autocom -d dicts/dict.json -c configs/config.json

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

| Device         | 内容                                | 作用                 |
| -------------- | ----------------------------------- | -------------------- |
| name           | 设备名称（如 "DeviceA"、"DeviceB"） | 标识不同的设备       |
| status         | 设备状态（"enabled"/"disabled"）    | 表示设备当前状态     |
| port           | 串口名称（如 "COM65"）              | 指定设备物理连接端口 |
| baud_rate      | 波特率（如 115200）                 | 设定通信速率         |
| stop_bits      | 停止位（1/2）                       | 设定停止位           |
| parity         | 奇偶校验（"None"/"Even"/"Odd"）     | 设定奇偶校验         |
| data_bits      | 数据位（5/6/7/8）                   | 设定数据位           |
| flow_control   | 流控制配置                          | 设定流控制           |
| dtr            | DTR信号（true/false）               | 设定DTR信号          |
| rts            | RTS信号（true/false）               | 设定RTS信号          |
| <u>monitor</u> | 是否持续监听设备（true/false）      | 设定是否持续监听日志 |

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

> 📖 **详细文档**: 查看 [docs/Actions.md](docs/Actions.md) 获取所有操作项的完整说明、参数详解和使用示例。
>
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

```python
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
```

首先先了解这个Action是指的什么。上面注释中所描述的`{ "test": "test_message" }`是一个Action项，也是一个Object对象，这个Action项的名称为`test`，而这个Action的内容则是`test_message`。在执行时，这个Action会被传入到`handle_test`函数中。
然后看看传入的参数列表：

① `self`这个是指向当前ActionHandler实例的引用，这里必须包含，用于注册ActionHandler的函数
② `text`这个是传入action所含的Object内容，这里是指`{"test": "test_message"}`中的`"test_message"`部分。如果action名包含的是一个Object对象，则会将该对象传入，这里需要注意类型对应。
③ `command`这个是指当前执行的指令对象，也就是指令字典中的`command`属性内容。
④ `response`这个是指当前指令执行后响应内容，<u>这个类型是`List`</u>,得注意。
⑤ `context`这个是指当前执行上下文，包含了当前设备、指令等信息。这里的context内容目前为：

```json
{
        "device": device,
        "device_name": device_name,
        "cmd_str": cmd_str,
        "expected_responses": updated_expected_responses
}
```

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

| Command                     | 内容                             | 作用                 |
| --------------------------- | -------------------------------- | -------------------- |
| <u>command</u>              | AT指令字符串（如 "AT+QRST"）     | 发送给设备的具体指令 |
| status                      | 指令状态（"enabled"/"disabled"） | 指定指令是否可用     |
| <u>expected_responses</u>   | 预期响应列表（如 ["OK","RDY"]）  | 判断指令执行成功条件 |
| device                      | 目标设备名称                     | 指定执行指令的设备   |
| order                       | 执行顺序（整数）                 | 确定指令执行顺序     |
| <u>parameters</u>           | 指令参数列表                     | 提供指令所需参数     |
| timeout                     | 超时时间（毫秒）                 | 设定指令执行时限     |
| concurrent_strategy         | "sequential"或"parallel"         | 设定指令并发策略     |
| **error_actions**           | 错误处理配置                     | 定义错误响应处理方式 |
| **success_actions**         | 成功后续操作                     | 指定成功后的附加动作 |
| **error_response_actions**  | 错误响应后续操作                 | 特定错误响应后的动作 |
| **success_response_actions**| 成功响应后续操作                 | 特定成功响应后的动作 |
| ~~dependencies~~            | 依赖指令列表                     | 设定指令执行依赖项   |

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
