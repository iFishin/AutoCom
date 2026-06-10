<!-- docs/MCP.md -->
# MCP Server（AI Agent 接口）

AutoCom 的 MCP Server 基于 Model Context Protocol 实现，允许 AI Agent（例如 Claude Desktop、Cursor、其他遵循 MCP 的客户端）通过 MCP 协议直接控制串口设备。

## 功能概览

- 支持 `list_devices`, `execute_command`, `execute_commands`, `load_dict`, `monitor_port` 等工具。
- 支持两种运行模式：`stdio`（默认，适用于本地桌面客户端）和 `SSE`（HTTP/SSE，适合远程或在服务器上运行）。

## 安装

自 vX 起，AutoCom 的 MCP Server 使用 `fastmcp` 作为运行时实现（替代早期的 `mcp` 实现）。请安装下列依赖：

```bash
pip install fastmcp pyserial pyyaml
# 可选：如果通过 extras 打包发布（如项目提供了 extras），也可使用
pip install autocom[mcp]
```

Windows 注意：串口相关依赖在 Windows 上可能需要 `pywin32`，若导入出现 `_win32sysloader` / pywintypes 相关的 DLL 错误，可尝试：

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

### Streamable (HTTP 双向流)

AutoCom 也支持 Streamable HTTP 传输（基于 mcp 的 Streamable transport），提供一个双向、长连接的消息通道，适用于需要持续双向通信或替代 SSE 的场景。

- 启动：

```bash
autocom mcp --streamable --port 8888 --host 0.0.0.0
```

- 主要端点：

  - 健康检查：`http://<host>:<port>/health`（返回 JSON 中 `transport` 字段为 `streamable`）
  - Streamable 入口：`/mcp/stream`（客户端通过该路径建立双向通道）

注意：使用 Streamable 模式需要安装 `fastmcp`（以及 `uvicorn`、`starlette` 等 HTTP 运行时依赖），通常通过 `pip install fastmcp` 或项目 extras 安装。

### 认证/鉴权

如果你在公网或不受信任的网络中暴露 MCP HTTP 接口，建议启用简单的 API Key 鉴权。使用 `--auth-key` 启动时，服务会要求每个请求携带 `Authorization: Bearer <key>` 或 `X-API-Key: <key>` 头部，否则返回 401。

示例：

```bash
autocom mcp --streamable --port 8888 --host 0.0.0.0 --auth-key s3cr3t
```

客户端示例（curl）：

```bash
curl -H "Authorization: Bearer s3cr3t" http://localhost:8888/health
```

## 可用工具（简要）

- `list_devices`：扫描并返回可用串口设备列表。
- `execute_command`：向指定串口发送单条指令并返回响应（参数：`port`, `command`, `baud_rate`, `timeout`, `hex_mode` 等）。
- `execute_commands`：批量执行多条指令，支持并行选项（参数：`port`, `commands[]`, `parallel`）。
- `load_dict`：加载 AutoCom 执行配置文件（JSON/YAML），返回解析结果（参数：`file_path`, `config_path`）。
- `validate_dict`：体检 AutoCom 执行配置文件，输出错误与告警（参数：`file_path`, `config_path`）。
- `monitor_port`：持续监听串口输出并返回一段时间内的采样数据（参数：`port`, `duration`）。
- `monitor_port_stream`：流式监听串口输出，返回持续的消息流用于实时推送（参数：`port`, `baud_rate`）。适用于 Streamable MCP 客户端。

`execute_command`/`execute_commands` 还支持高级参数：

- `expected_responses`：字符串数组，命中后可提前结束采集并返回 `matched`。
- `completion_rules`：完成判定规则对象。
  - `expected_required`：为 true 时必须命中 expected 才完成。
  - `terminal_patterns`：终止词，默认 `["OK", "ERROR"]`。
  - `complete_patterns`：自定义完成词，任意命中即可完成。
  - `idle_timeout`：响应空闲收敛超时（秒）。
  - `settle_after_terminal`：命中终止词后额外收敛等待（秒）。
- `priority`：命令优先级（用于与 monitor 场景调度对齐，默认 0）。

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

## 安全部署与鉴权最佳实践

当在不受信任网络或公网中暴露 HTTP（SSE/Streamable）接口时，建议遵循下列安全实践：

- 使用反向代理 + TLS：将 `autocom mcp --sse|--streamable` 放在可信的反向代理（例如 Nginx/Traefik）之后，终端对外暴露 TLS（HTTPS）。

- 将服务绑定到内网接口：在生产环境尽量避免直接绑定 `0.0.0.0`，若必须对外暴露请配合防火墙/安全组限制访问。

- 使用 API Key（已支持 `--auth-key`）：服务支持通过 `--auth-key` 启用简单的 API Key 鉴权，要求客户端为每个请求添加 `Authorization: Bearer <key>` 或 `X-API-Key: <key>`。

- 将密钥存储在环境变量或秘密管理系统中：不要把密钥写入代码或公开仓库。示例（Linux）：

```bash
export AUTOCOM_AUTH_KEY=s3cr3t
autocom mcp --streamable --port 8888 --host 127.0.0.1 --auth-key "$AUTOCOM_AUTH_KEY"
```

- 限制和监控访问：启用反向代理的访问日志、IP 限速（rate limiting）、请求频率限制，并对异常请求触发告警。

- 使用 VPN / 内网隧道：将管理接口放在私有网络中，通过 VPN、SSH 隧道或安全网关访问。

- 避免在公共网络下启用 `stdio` 模式：`stdio` 模式适用于本地桌面客户端（如 Claude Desktop），不应作为对外 HTTP 的替代方式。

- 定期轮换密钥与审计：定期更换 API Key，并记录客户端访问日志以便审计。

示例 Nginx 反向代理（简要）：

```nginx
server {
  listen 443 ssl;
  server_name autocom.example.com;

  ssl_certificate /etc/ssl/certs/fullchain.pem;
  ssl_certificate_key /etc/ssl/private/privkey.pem;

  location / {
    proxy_pass http://127.0.0.1:8888;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_set_header Connection "";
  }
}
```

更多安全建议可参考你的基础设施安全实践（TLS、WAF、网络策略）。
