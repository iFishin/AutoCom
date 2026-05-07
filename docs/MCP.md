<!-- docs/MCP.md -->
# MCP Server（AI Agent 接口）

AutoCom 的 MCP Server 基于 Model Context Protocol 实现，允许 AI Agent（例如 Claude Desktop、Cursor、其他遵循 MCP 的客户端）通过 MCP 协议直接控制串口设备。

## 功能概览

- 支持 `list_devices`, `execute_command`, `execute_commands`, `load_dict`, `monitor_port` 等工具。
- 支持两种运行模式：`stdio`（默认，适用于本地桌面客户端）和 `SSE`（HTTP/SSE，适合远程或在服务器上运行）。

## 安装

推荐通过 extras 安装 MCP 相关依赖：

```bash
pip install autocom[mcp]
```

或单独安装 MCP：

```bash
pip install mcp
```

> Windows 注意：MCP 及其依赖在 Windows 上可能依赖 `pywin32` 的本机 DLL，若导入出现 `_win32sysloader` / pywintypes 相关的 DLL 错误，可尝试重装 `pywin32` 并运行 postinstall 脚本：

```powershell
python -m pip install --upgrade pywin32
python -m pywin32_postinstall -install
```

## 启动方式

- Stdio（默认，适用于 Claude Desktop）

```bash
autocom mcp
```

- SSE (HTTP) 模式

```bash
autocom mcp --sse --port 8888 --host 0.0.0.0
```

启动后可用的端点与说明：

- 健康检查：`http://<host>:<port>/health`
- MCP SSE 入口：`/mcp/sse`（用于 MCP Inspector 或远端客户端）

## 可用工具（简要）

- `list_devices`：扫描并返回可用串口设备列表。
- `execute_command`：向指定串口发送单条指令并返回响应（参数：`port`, `command`, `baud_rate`, `timeout`, `hex_mode` 等）。
- `execute_commands`：批量执行多条指令，支持并行选项（参数：`port`, `commands[]`, `parallel`）。
- `load_dict`：加载 AutoCom 字典文件（JSON/YAML），返回解析结果（参数：`file_path`, `config_path`）。
- `monitor_port`：持续监听串口输出并返回一段时间内的采样数据（参数：`port`, `duration`）。

## 在 Claude Desktop 中配置示例

在 Claude Desktop 的配置中添加：

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

## 调试与常见问题

- 若 `mcp` 导入失败：请检查当前 Python 环境中是否安装了 `mcp`，以及 Windows 下 `pywin32` 是否正确安装并运行了 postinstall。
- 若希望避免在未安装 `mcp` 时导入整个包，请使用 CLI 子命令 `autocom mcp`（该路径在运行时才会尝试导入 MCP 相关模块）。

---

更多实现细节请参考代码：`components/MCPServer.py`
