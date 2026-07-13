---
name: autocom-api
label: AutoCom REST API 助手
description: 通过 HTTP 接口远程操作 AutoCom——串口调试、持久会话、硬件诊断、流水线执行、执行历史查询。触发关键词：发送指令/打开串口/扫描波特率/执行流水线/查看历史/回环测试/延迟测试。
---

# AutoCom REST API 助手

## 用途

通过 HTTP 远程操作 AutoCom 的所有功能，适合集成到自动化脚本、CI/CD 管道、Web 应用或其他工具中。所有接口都可通过 `http://localhost:8000/docs` 的 Swagger UI 交互式调试。

## 接口分组

### 串口操作

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/ports` | 列出可用串口 |
| POST | `/api/ports/{port}/command` | 发单条指令 |
| POST | `/api/ports/{port}/baud-scan` | 扫描波特率 |
| GET | `/api/ports/{port}/hex-dump` | hex 查看数据 |
| GET | `/api/ports/{port}/pin-status` | 读信号线状态 |
| POST | `/api/ports/{port}/pin-set` | 设 DTR/RTS |
| POST | `/api/ports/{port}/loopback` | 回环测试 |
| POST | `/api/ports/{port}/latency` | 延迟基准测试 |
| WS | `/api/ports/{port}/monitor` | 实时监视 |

### 持久会话

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/sessions` | 打开会话 |
| GET | `/api/sessions` | 列出会话 |
| DELETE | `/api/sessions/{id}` | 关闭会话 |
| POST | `/api/sessions/{id}/send` | 发指令 |
| POST | `/api/sessions/{id}/read` | 读缓冲区 |

### 设备配置 / 流水线存储

| 方法 | 路径 | 用途 |
|------|------|------|
| GET/POST/DELETE | `/api/profiles` | 设备参数 CRUD |
| GET/POST/DELETE | `/api/storage/pipelines` | 流水线文件管理 |

### 流水线执行

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/pipeline/validate\|run\|dry-run\|step-debug` | 校验/执行/干跑/单步调试 |

### 执行历史

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/executions` | 列出所有执行记录 |
| GET | `/api/executions/search?keyword=xxx` | 全局日志搜索 |
| GET | `/api/executions/{id}` | 查看详情（`?filename=DeviceA.log` 下载原始日志） |
| GET | `/api/executions/{id}/search?keyword=xxx` | 在指定会话内搜索 |

## 参数说明

参考 `references/params.md` 查看每个接口的参数详情。

## 典型调用流程

### 快速诊断

```python
import httpx
api = "http://localhost:8000"

# 1. 查端口
ports = httpx.get(f"{api}/api/ports").json()
port = ports["devices"][0]["device"]

# 2. 发指令
r = httpx.post(f"{api}/api/ports/{port}/command", params={"command": "AT"})
print(r.json()["response"])

# 3. 查信号线
r = httpx.get(f"{api}/api/ports/{port}/pin-status")
print(r.json())
```

### 持久会话交互

```python
# 打开
s = httpx.post(f"{api}/api/sessions", params={"port": "COM16", "baud_rate": 115200}).json()
sid = s["session_id"]

# 多发几条
httpx.post(f"{api}/api/sessions/{sid}/send", params={"command": "AT"})
httpx.post(f"{api}/api/sessions/{sid}/send", params={"command": "AT+CSQ"})

# 读缓冲
r = httpx.post(f"{api}/api/sessions/{sid}/read")
print(r.json()["data"])

# 关闭
httpx.delete(f"{api}/api/sessions/{sid}")
```

### 流水线执行

```python
# 先保存流水线配置
httpx.post(f"{api}/api/storage/pipelines?name=my_test",
    json={"content": "Devices:\n  - name: DUT\n    port: COM16\n    baud_rate: 115200\n\nSteps:\n  - id: check\n    type: serial\n    device: DUT\n    send: AT\n    expect: ['OK']\n"})

# 校验
r = httpx.post(f"{api}/api/pipeline/validate", params={"name": "my_test"})

# 执行
r = httpx.post(f"{api}/api/pipeline/run", params={"name": "my_test", "loop_count": 5})
print(r.json()["results"])  # step-by-step results
```

### 日志检索与排查

```python
# 全局搜索（跨所有会话和操作日志）
r = httpx.get(f"{api}/api/executions/search", params={"keyword": "FAIL"})
for m in r.json()["matches"]:
    print(f"[{m['session_id']}] {m['file']}:{m['line']} {m['text']}")

# 指定会话内搜索
r = httpx.get(f"{api}/api/executions/2026-07-13_14-30-00/search",
    params={"keyword": "FAIL"})

# 查执行详情 + 下载原始日志
r = httpx.get(f"{api}/api/executions/2026-07-13_14-30-00").json()
print(r["summary"])       # passed/failed 统计
print(r["step_results"])  # 步骤执行结果
print(r["device_logs"])   # 日志文件列表

# 下载原始日志文件
raw = httpx.get(f"{api}/api/executions/2026-07-13_14-30-00",
    params={"filename": "DeviceA_COM16.log"}).text
```

## 调用方式

参考 `examples/` 目录下的完整示例。