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

### 设备配置 / 流水线 / 执行历史

| 方法 | 路径 | 用途 |
|------|------|------|
| GET/POST/DELETE | `/api/profiles` | 设备参数 CRUD |
| GET | `/api/pipelines` | 列出配置文件 |
| POST | `/api/pipeline/validate\|run\|dry-run\|step-debug` | 流水线操作 |
| GET | `/api/executions` | 执行历史 |

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
# 校验
r = httpx.post(f"{api}/api/pipeline/validate", params={"file_path": "dicts/test.yaml"})

# 执行
r = httpx.post(f"{api}/api/pipeline/run", params={"file_path": "dicts/test.yaml", "loop_count": 5})
```

### 排查失败

```python
# 看历史
r = httpx.get(f"{api}/api/executions", params={"limit": 5})
sid = r.json()["sessions"][0]["session_id"]

# 搜关键词
r = httpx.get(f"{api}/api/executions/{sid}/search", params={"keyword": "FAIL"})
for m in r.json()["matches"]:
    print(f"{m['file']}:{m['line']} {m['text']}")
```

## 调用方式

参考 `examples/` 目录下的完整示例。