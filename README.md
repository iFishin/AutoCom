<div align="center">

# AutoCom

*通用流水线自动化执行工具 —— 串口 / HTTP / 本地脚本 / 混合编排*

![Cross Platform](https://img.shields.io/badge/cross--platform-Windows%20%26%20Linux-success.svg)
![Pipeline](https://img.shields.io/badge/type-Pipeline%20Automation-blue.svg)
![PyPI](https://img.shields.io/badge/PyPI-autocom-blue.svg)

</div>

---

## 📦 安装

```bash
pip install autocom
```

或从源码安装：

```bash
git clone https://github.com/iFishin/AutoCom.git
cd AutoCom
pip install -e .
```

---

## 🚀 快速开始

### 执行流水线

```bash
# 单次执行（Config 块声明执行方式）
autocom -p dicts/AutoCom2_Dicts/action_batch_demo.yaml

# 指定循环轮数
autocom -p pipeline.yaml -n 5

# 限时执行（30秒/5分钟/1小时，自动停止）
autocom -p pipeline.yaml --duration 30s

# 轮数与时长双重限制，先到先停
autocom -p pipeline.yaml -n 100 --duration 10m

# 批量执行文件夹
autocom -f dicts/

# 监控模式，新文件自动执行
autocom -m temps/
```

### 流水线配置文件示例（新 Steps 格式）

```yaml
Config:
  description: "固件升级 + 云端上报"
  mode: single

Devices:
  - name: DeviceA
    port: COM66
    baud_rate: 115200

Steps:
  - id: check_fw
    type: serial
    device: DeviceA
    send: AT+QVERSION
    expect: ["OK"]
    capture:
      version: "Version: (\\d+\\.\\d+\\.\\d+)"

  - id: check_ota
    type: http
    url: "http://ota.example.com/check?fw={{ steps.check_fw.capture.version }}"

  - id: health_check
    type: script
    command: pytest tests/diag.py
    on_error: skip

  - id: report
    type: action_batch
    actions:
      - save:
          to: constants.result
          value: "done"
      - print: "流水线完成"
```

### 支持的控制流

```yaml
- id: check_network
  type: serial
  send: AT+CREG?
  expect: ["+CREG: 1"]
  on_error: goto(troubleshoot)    # 失败跳转
  on_success: continue            # 成功继续

- id: process_data
  type: script
  command: python parse.py
  if: "{{ steps.check_network.capture.rssi }} >= 20"  # 条件跳过
  on_error: retry(3)              # 失败重试 3 次
```

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| **Steps 流水线** | 每一步独立定义类型，不限串口 |
| **串口 (serial)** | AT 指令、expect 匹配、capture 变量提取 |
| **HTTP (http)** | GET/POST/PUT/DELETE、status_code/body 校验 |
| **脚本 (script)** | subprocess 执行、stdout 捕获、exit_code 校验 |
| **Action 批处理 (action_batch)** | 纯逻辑操作，无需 I/O |
| **控制流** | `if` / `unless` 条件跳过、`on_error: retry/goto/abort` |
| **模板变量** | `{{ steps.xxx.capture.yyy }}` 精确路径 / `{VAR}` 模糊搜索 |
| **类型感知存储** | 变量保持 int/float/bool/json 类型写 SQLite |
| **向后兼容** | 旧 `Commands[]` 格式自动转换为 `type: serial` Steps |

---

## 📁 项目结构

```
AutoCom/
├── components/
│   ├── SessionStore.py       # SQLite 持久化层（替代旧 JSON DataStore）
│   ├── Context.py             # 运行时变量上下文
│   ├── PipelineScheduler.py   # 流水线调度器（程序计数器 + 控制流）
│   ├── steps/                 # 各 type 的 Handler
│   │   ├── serial.py
│   │   ├── http.py
│   │   ├── script.py
│   │   ├── wait.py
│   │   └── action_batch.py
│   ├── CommandExecutor.py     # 旧兼容层（保留 execute_command()）
│   ├── Device.py              # 串口设备抽象
│   └── Logger.py              # 日志系统
├── utils/
│   ├── TemplateEngine.py      # 变量解析 + 条件评估
│   ├── ActionHandler.py       # Action 分发系统
│   └── dirs.py                # 路径管理
├── dicts/
│   └── AutoCom2_Dicts/        # 新格式示例配置文件
├── docs/
│   ├── Started.md             # 开发指南
│   └── MCP.md                 # MCP Server 文档
├── data/
│   └── sessions.db            # SQLite 执行记录
├── cli.py                     # CLI 入口
└── AutoCom.py                 # 主执行引擎
```

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [docs/Started.md](docs/Started.md) | 开发快速指南与发布流程 |
| [docs/About.md](docs/About.md) | 项目背景与设计理念 |
| [docs/Actions.md](docs/Actions.md) | 所有 Action 操作项的详细说明 |
| [docs/MCP.md](docs/MCP.md) | MCP Server: AI Agent 接口 |
| [dicts/AutoCom2_Dicts/](dicts/AutoCom2_Dicts/) | 7 个新格式示例文件 |

---

## 🌐 MCP Server（AI Agent 接口）

```bash
pip install autocom[mcp]
autocom mcp                     # Claude Desktop 集成
autocom mcp --sse --port 8888   # HTTP 模式
```

详情参见 [docs/MCP.md](docs/MCP.md)。

---

## 🌍 REST API（HTTP 接口）

通过 FastAPI 提供完整的 HTTP REST 接口，自动生成 Swagger UI 文档。

```bash
pip install autocom[api]
autocom api                          # 默认端口 8000
autocom api --port 8080              # 自定义端口
autocom api --host 127.0.0.1         # 仅本地访问
```

启动后浏览器打开 `http://localhost:8000/docs` 即可查看和调试所有接口。

### 接口分类

```
端口操作     GET/POST  /api/ports/{port}/command|baud-scan|hex-dump|pin-status|...
实时监视     WS        /api/ports/{port}/monitor
持久会话     POST/GET/DELETE  /api/sessions   +  /api/sessions/{id}/send|read
设备配置     GET/POST/DELETE  /api/profiles
流水线       POST      /api/pipeline/run|validate|dry-run|step-debug
执行历史     GET       /api/executions  +  /api/executions/{id}/search
```

也可以用 curl 调用：

```bash
# 列出串口
curl http://localhost:8000/api/ports

# 发送 AT 指令
curl -X POST "http://localhost:8000/api/ports/COM16/command?command=AT&baud_rate=115200"

# 列出执行历史
curl "http://localhost:8000/api/executions?limit=5"
```

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

MIT License © 2026 iFishin
