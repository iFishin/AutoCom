# AutoCom REST API 参考

## 基本信息

- **Base URL**: `http://{host}:{port}`
- **Swagger UI**: `http://{host}:{port}/docs`
- **Content-Type**: `application/json`

---

## 系统

### GET /api/health

健康检查。

```json
// Response
{"status": "ok", "version": "2.0.0", "sessions": 0}
```

---

## 串口操作

### GET /api/ports

列出可用串口设备。

```json
// Response
{
  "success": true,
  "total": 1,
  "devices": [
    {"device": "COM16", "description": "USB Serial Port", "hwid": "USB\\...", "vid": 1234, "pid": 5678}
  ]
}
```

### POST /api/ports/{port}/command

发送单条指令。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `port` | path | — | 串口号 |
| `command` | query | — | 要发送的指令 |
| `baud_rate` | query | 115200 | 波特率 |
| `timeout` | query | 5.0 | 响应超时（秒） |
| `line_ending` | query | 0d0a | 行结尾 hex 字节 |
| `hex_mode` | query | false | 是否 hex 模式 |

```json
// Response
{"success": true, "port": "COM16", "command": "AT", "response": "AT\r\nOK\r\n", "elapsed_ms": 15}
```

cURL:

```bash
curl -X POST "http://localhost:8000/api/ports/COM16/command?command=AT&baud_rate=115200"
```

### POST /api/ports/{port}/baud-scan

自动扫描波特率（9600~921600）。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `port` | path | — | 串口号 |
| `body.test_command` | body | "AT" | 测试指令 |
| `body.expected_response` | body | "OK" | 期望响应 |
| `body.line_ending` | body | "0d0a" | 行结尾 |

```json
// Response
{"success": true, "port": "COM16", "working_rates": [115200], "results": [...]}
```

cURL:

```bash
curl -X POST "http://localhost:8000/api/ports/COM16/baud-scan" \
  -H "Content-Type: application/json" \
  -d '{"test_command": "AT", "expected_response": "OK"}'
```

### GET /api/ports/{port}/hex-dump

以 hex+ASCII 读取串口数据。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `port` | path | — | 串口号 |
| `baud_rate` | query | 115200 | 波特率 |
| `bytes_to_read` | query | 256 | 读取字节数 |
| `timeout` | query | 3.0 | 超时（秒） |

```json
// Response
{
  "success": true,
  "bytes_read": 256,
  "hex_dump": [{"offset": 0, "hex": "41 54 0d 0a ...", "ascii": "AT..", "raw": [65, 84, 13, 10]}],
  "raw_bytes": [65, 84, 13, 10],
  "text": "AT\r\n..."
}
```

### GET /api/ports/{port}/pin-status

读取 CTS/DSR/DCD/RI 信号线状态。

```json
// Response
{"success": true, "port": "COM16", "cts": true, "dsr": true, "dcd": false, "ri": false}
```

### POST /api/ports/{port}/pin-set

设置 DTR/RTS 输出电平。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `dtr` | query | null | true/false |
| `rts` | query | null | true/false |

### POST /api/ports/{port}/loopback

串口回环测试。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `mode` | query | hardware | `hardware`（需短接 TX/RX）或 `echo`（发指令等回复） |
| `test_data` | query | null | 硬件回环测试数据 |
| `probe_command` | query | AT | 回声测试指令 |
| `probe_expected` | query | OK | 期望响应 |

### POST /api/ports/{port}/latency

延迟基准测试。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `rounds` | query | 10 | 测试轮数 |

```json
// Response
{
  "success": true, "rounds": 10, "errors": 0,
  "tx_latency_ms": {"min": 0.2, "max": 0.4, "avg": 0.3},
  "first_byte_latency_ms": {"min": 2.5, "max": 4.0, "avg": 3.1},
  "rtt_ms": {"min": 8.2, "max": 15.1, "avg": 10.5}
}
```

---

## 持久会话

持久会话打开后保持连接，适合多轮交互。

### POST /api/sessions

打开会话。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `port` | query | — | 串口号 |
| `baud_rate` | query | 115200 | 波特率 |
| `timeout` | query | 5.0 | 读取超时（秒） |
| `label` | query | null | 会话标签 |

```json
// Response
{"success": true, "session_id": "sess_a1b2c3d4e5f6", "port": "COM16", "baud_rate": 115200, "label": "COM16@115200"}
```

### GET /api/sessions

列出活跃会话。

### GET /api/sessions/{session_id}

获取会话详情。

### DELETE /api/sessions/{session_id}

关闭会话。

### POST /api/sessions/{session_id}/send

在会话中发送指令。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `command` | query | — | 要发送的指令 |
| `timeout` | query | null | 响应超时覆盖 |
| `line_ending` | query | 0d0a | 行结尾 |

```json
// Response
{"success": true, "command": "AT", "response": "AT\r\nOK\r\n", "elapsed_ms": 12, "bytes": 9}
```

### POST /api/sessions/{session_id}/read

读取会话缓冲区。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `timeout` | query | null | 等待超时 |
| `max_bytes` | query | null | 最大读取字节数 |

```json
// Response
{"success": true, "data": "URC: WIFI_DISCONNECTED\r\n", "bytes_count": 28, "session_id": "sess_..."}
```

---

## 设备配置

保存常用串口参数，按名称快速复用。

### GET /api/profiles

列出已保存的配置。

### POST /api/profiles

保存配置。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `name` | query | — | 唯一标识名 |
| `port` | query | — | COM 端口 |
| `baud_rate` | query | 115200 | 波特率 |
| `data_bits` | query | 8 | 数据位 |
| `stop_bits` | query | 1 | 停止位 |
| `parity` | query | none | none/even/odd/mark/space |
| `flow_control` | query | false | RTS/CTS 流控 |
| `timeout` | query | 5.0 | 超时 |
| `label` | query | "" | 显示标签 |

### DELETE /api/profiles/{name}

删除配置。

---

## 流水线

### GET /api/pipelines

列出流水线配置文件。可选 `base_dir` 参数指定搜索目录。

### POST /api/pipeline/validate

校验流水线配置。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `file_path` | query | — | 配置文件路径 |
| `config_path` | query | null | 覆盖文件路径 |
| `config_overrides` | query | null | JSON 覆盖 |

### POST /api/pipeline/run

执行流水线。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `file_path` | query | — | 配置文件路径 |
| `loop_count` | query | null | 循环轮数 |
| `duration` | query | null | 限时: 30s/5m/1h |
| `stop_on_failure` | query | null | 失败即停止 |
| `config_overrides` | query | null | JSON 覆盖 |

### POST /api/pipeline/dry-run

干运行（不执行 I/O）。

### POST /api/pipeline/step-debug

单步调试。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `file_path` | query | — | 配置文件路径 |
| `step_id` | query | — | 步骤 ID |

---

## 执行历史

### GET /api/executions

列出执行记录。可选 `limit` 参数控制返回条数。

```json
// Response
{
  "success": true, "total": 5,
  "sessions": [
    {"session_id": "2026-07-08_14-30-00", "path": "D:\\...", "has_log": true, "has_json": false, "device_logs": ["DeviceA.log"], "device_count": 1}
  ]
}
```

### GET /api/executions/{session_id}

查看执行详情（日志、设备日志、摘要）。

### GET /api/executions/{session_id}/search?keyword=FAIL

在设备日志中搜索关键词。

```json
// Response
{"success": true, "keyword": "FAIL", "total_matches": 3, "matches": [{"file": "EXECUTION.log", "line": 42, "text": "[FAIL] Step connect_wifi failed (timeout)"}]}
```

---

## 调用方式总结

```python
# Python httpx 示例
import httpx

BASE = "http://localhost:8000"

# 列出串口
ports = httpx.get(f"{BASE}/api/ports").json()

# 发送指令
r = httpx.post(f"{BASE}/api/ports/COM16/command", params={
    "command": "AT", "baud_rate": 115200
}).json()
print(r["response"])  # "AT\r\nOK\r\n"

# 打开会话
sess = httpx.post(f"{BASE}/api/sessions", params={
    "port": "COM16", "baud_rate": 115200
}).json()
sid = sess["session_id"]

# 会话中发指令
r = httpx.post(f"{BASE}/api/sessions/{sid}/send", params={
    "command": "AT+CSQ"
}).json()
print(r["response"])

# 关闭会话
httpx.delete(f"{BASE}/api/sessions/{sid}")

# 执行流水线
r = httpx.post(f"{BASE}/api/pipeline/run", params={
    "file_path": "dicts/softap_steps.yaml"
}).json()
```
