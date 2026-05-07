<div align="center">

# AutoCom

*一款用于自动化执行串口指令的命令行工具，支持多设备、多指令的串行和并行执行。*

![Cross Platform](https://img.shields.io/badge/cross--platform-Windows%20%26%20Linux-success.svg)
![Serial Communication](https://img.shields.io/badge/communication-Serial%20Port-orange.svg)
![Multi-Device](https://img.shields.io/badge/support-Multi--Device-blueviolet.svg)
![Automation](https://img.shields.io/badge/type-Automation%20Tool-red.svg)
![PyPI](https://img.shields.io/badge/PyPI-autocom-blue.svg)

</div>

---

## 📦 安装

### 从 PyPI 安装（推荐）

```bash
pip install autocom
```

### 从 GitHub 直接安装

```bash
pip install git+https://github.com/iFishin/AutoCom.git
```

### 从源码安装

```bash
git clone https://github.com/iFishin/AutoCom.git
cd AutoCom
pip install -r requirements.txt
pip install -e .
```

---

## 🚀 快速开始

### 命令行使用

```bash
# 初始化项目结构（创建 dicts/、configs/、temps/ 目录及示例文件）
autocom --init

# 执行字典文件（循环3次）
autocom -d dicts/dict.yaml -l 3

# 无限循环模式（按 Ctrl+C 停止）
autocom -d dicts/dict.yaml -i

# 使用配置文件
autocom -d dicts/dict.yaml -c configs/config.yaml

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

## 📁 项目结构

```plain
AutoCom/
├── components/         # 核心组件模块（Device、Logger、TablePrinter、CommandDeviceDict、DataStore、CommandExecutor）
├── utils/              # 工具类和辅助函数（ActionHandler、common、dirs）
├── tests/              # 测试文件
├── scripts/            # 构建和维护脚本（dev.py、update_actions_doc.py）
├── docs/               # 项目文档
├── dicts/              # 字典配置文件目录
├── configs/            # 设备配置文件目录
├── AutoCom.py          # 主程序入口
├── cli.py              # 命令行接口
├── version.py          # 版本信息
└── CHANGELOG.md        # 变更日志
```

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [docs/About.md](docs/About.md) | 项目背景与设计理念 |
| [docs/Started.md](docs/Started.md) | 开发快速指南与发布流程 |
| [docs/Actions.md](docs/Actions.md) | 所有 Action 操作项的详细说明 |
| [docs/DEV.md](docs/DEV.md) | 开发工具使用说明 |
| [docs/ToDO.md](docs/ToDO.md) | 待办事项与未来计划 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更历史 |
| [docs/MCP.md](docs/MCP.md) | MCP Server: AI Agent 接口 |

> 📖 **格式框架详解**（Devices、Commands、Actions 的 JSON 格式说明）参见 [docs/About.md](docs/About.md)。

---

## 🔧 核心功能

| 功能 | 说明 |
|------|------|
| 多设备支持 | 同时管理多个串口设备，支持不同配置 |
| 串行/并行执行 | 指令可按顺序执行或并行并发执行 |
| Action 扩展系统 | 通过 ActionHandler 自定义指令成功/失败后的处理逻辑 |
| 配置覆盖机制 | ConfigForDevices / ConfigForCommands 简化重复配置 |
| 常量和变量 | Constants 支持用户输入变量，在指令参数中引用 |
| 文件夹遍历 | 批量执行文件夹内所有字典文件 |
| 监控模式 | 监听文件夹，新文件自动执行 |
| 持续日志监听 | 后台线程持续记录串口输出 |
| **MCP Server** | **为 AI Agent 提供串口操作接口，支持 Claude Desktop 等 MCP 客户端** |

---

## 🤖 MCP Server（AI Agent 接口）

AutoCom MCP Server 基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 实现，让 AI Agent（如 Claude Desktop、Cursor 等）能够直接控制串口设备。

### 安装

```bash
# 安装 MCP 依赖
pip install autocom[mcp]
```

### 启动

```bash
# Stdio 模式（默认，适合 Claude Desktop）
autocom mcp

# SSE (HTTP) 模式（适合远程调用）
autocom mcp --sse --port 8888
```

### 可用的 MCP 工具

| 工具名 | 描述 | 关键参数 |
|--------|------|----------|
| `list_devices` | 列出可用串口设备 | 无需参数 |
| `execute_command` | 发送单条指令并获取响应 | `port`, `command`, `baud_rate`(可选) |
| `execute_commands` | 批量执行多条指令 | `port`, `commands[]`, `parallel`(可选) |
| `load_dict` | 加载 AutoCom 字典 JSON 配置 | `file_path`, `config_path`(可选) |
| `monitor_port` | 监听串口输出 | `port`, `duration`(可选) |

### 配置 Claude Desktop

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "autocom": {
      "command": "autocom",
      "args": ["mcp"]
    }
  }
}
```

### SSE 模式

SSE 模式启动后可通过浏览器或 MCP Inspector 调试：

```
# 健康检查
http://localhost:8888/health

# MCP Inspector 调试
npx @modelcontextprotocol/inspector
# 连接地址: http://localhost:8888/mcp/sse
```

### 使用示例（Python API）

```python
# 扫描设备
result = await client.call_tool("list_devices", {})

# 发送指令
result = await client.call_tool("execute_command", {
    "port": "COM3",
    "command": "AT+GMR",
    "baud_rate": 115200,
    "timeout": 5.0,
})

# 批量执行
result = await client.call_tool("execute_commands", {
    "port": "/dev/ttyUSB0",
    "commands": ["AT", "AT+GMR", "AT+CSQ"],
    "parallel": False,
})
```

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

MIT License © 2025 iFishin
