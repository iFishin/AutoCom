# AutoCom Steps 格式规范

## 顶层结构

```yaml
Config: { ... }       # 执行配置（可选）
Devices: [ ... ]       # 设备列表（必填，纯 HTTP/action 流程可至少 1 个）
Constants: { ... }     # 共享变量（可选）
Steps: [ ... ]         # 步骤列表（必填，至少 1 个）
```

---

## Devices（设备）

每个设备条目：

| 字段 | 类型 | 必填 | 说明 |
|-------|------|----------|-------------|
| `name` | string | ✅ | 唯一设备名，被 Steps[*].device 引用 |
| `port` | string | ✅ | 串口号（例如 COM16, /dev/ttyUSB0） |
| `baud_rate` | int | ✅ | 波特率（例如 115200） |
| `status` | string | ❌ | `"enabled"`（默认）或 `"disabled"` |
| `stop_bits` | int | ❌ | 默认 1 |
| `parity` | string | ❌ | `null`（无）、`"N"`、`"E"`、`"O"`、`"M"`、`"S"` |
| `data_bits` | int | ❌ | 默认 8 |
| `flow_control` | object | ❌ | 见下方，默认全部 false |
| `dtr` | bool | ❌ | 默认 false |
| `rts` | bool | ❌ | 默认 false |
| `monitor` | bool | ❌ | 启用被动串口监视（捕获主动上报消息） |

### flow_control 默认值

```yaml
flow_control:
  xon_xoff: false
  rts_cts: false
  dsr_dtr: false
```

---

## Config（配置）

```yaml
Config:
  description: "My pipeline"        # 自由文本描述
  mode: single                      # "single"（单次）或 "loop"（循环）
  loop:
    iterations: 100                 # 最大迭代次数（也可用 CLI -n）
    duration: "30m"                 # 自动停止前的最大时长
    interval_ms: 5000               # 迭代间隔毫秒数
    stop_on_failure: false          # true = 首次失败即中止
```

### 简写形式

```yaml
# 等同于 Config: { mode: loop, loop: { iterations: 10 } }
loop: 10
```

---

## Steps（步骤）

流水线的核心。每个步骤执行一个动作。

### 公共字段（所有类型）

| 字段 | 类型 | 必填 | 说明 |
|-------|------|----------|-------------|
| `id` | string | ✅ | 唯一步骤标识符 |
| `name` | string | ❌ | 人类可读的标签 |
| `type` | string | ✅ | `serial`, `serial_wait`, `http`, `script`, `wait`, `action_batch`, `goto` |
| `order` | int | ❌ | 执行顺序（数字越小越先执行）。省略时自动分配 |
| `if` | string | ❌ | 条件表达式 — 如果为 false 则跳过该步骤 |
| `unless` | string | ❌ | 条件表达式 — 如果为 true 则跳过该步骤 |
| `on_error` | string/object | ❌ | 错误处理策略（见下方） |
| `on_success` | string | ❌ | 成功处理：`continue`（默认）或 `goto(id)` |
| `timeout` | int | ❌ | 步骤超时**秒数**（不同步骤类型有不同默认值） |

### `on_error` 取值

| 值 | 行为 |
|-------|----------|
| `retry(3)` | 失败后最多重试 3 次，然后继续 |
| `goto(step_id)` | 失败后跳转到指定步骤 |
| `skip` | 失败后静默跳过该步骤 |
| `abort` | （默认）失败后中止整个流水线 |

### `on_success` 取值

| 值 | 行为 |
|-------|----------|
| （省略） | 继续执行下一步（默认） |
| `goto(step_id)` | 成功后跳转到指定步骤 |

---

### 步骤类型：`serial`

通过串口发送 AT 指令并匹配响应。

```yaml
- id: check_fw
  type: serial
  device: DeviceA
  send: "AT+QVERSION"
  expect: ["OK"]
  timeout: 5
  capture:
    version: "Version: (.+)"
```

| 字段 | 类型 | 必填 | 说明 |
|-------|------|----------|-------------|
| `device` | string | ✅ | Devices 列表中的设备名 |
| `send` | string | ✅ | 要发送的数据（AT 指令或原始文本） |
| `expect` | list[string] | ❌ | 响应中包含**任意一个**即视为成功 |
| `timeout` | int | ❌ | 等待响应的秒数（默认设备超时时间） |
| `capture` | object | ❌ | 从响应中提取值的正则表达式 |
| `hex_mode` | bool | ❌ | 以十六进制字节发送数据 |

### 步骤类型：`serial_wait`

被动监听设备的期望字符串（不发送数据）。

```yaml
- id: wait_ap_connect
  type: serial_wait
  device: DeviceA
  expect: ["AP_CONNECT"]
  timeout: 10
```

### 步骤类型：`http`

发起 HTTP 请求。

```yaml
- id: check_ota
  type: http
  url: "{{ constants.API_BASE }}/status"
  method: GET
  headers:
    Authorization: "Bearer token123"
  expect:
    status_code: 200
    body_match: '"ok"'
  capture:
    version: '"version": "(.+?)"'
  timeout: 10
```

| 字段 | 类型 | 必填 | 说明 |
|-------|------|----------|-------------|
| `url` | string | ✅ | 请求 URL（支持模板变量） |
| `method` | string | ❌ | `GET`（默认）、`POST`、`PUT`、`DELETE` |
| `headers` | object | ❌ | HTTP 请求头 |
| `body` | any | ❌ | POST/PUT 的请求体 |
| `expect.status_code` | int | ❌ | 期望的 HTTP 状态码 |
| `expect.body_match` | string | ❌ | 响应体中期望的字符串片段 |
| `capture` | object | ❌ | 从响应体中提取值的正则表达式 |
| `timeout` | int | ❌ | 秒数（默认 10） |

### 步骤类型：`script`

运行本地进程。

```yaml
- id: run_diag
  type: script
  command: python tests/health_check.py --imei {{ steps.get_imei.capture.imei }}
  shell: true
  timeout: 30
  capture:
    result: '(PASS|FAIL): (.+)'
```

| 字段 | 类型 | 必填 | 说明 |
|-------|------|----------|-------------|
| `command` | string | ✅ | 要执行的命令 |
| `shell` | bool | ❌ | 通过 shell 运行（默认 false） |
| `timeout` | int | ❌ | 秒数（默认 30） |
| `capture` | object | ❌ | 从 stdout 提取值的正则表达式 |

### 步骤类型：`wait`

纯延时。

```yaml
- id: settle
  type: wait
  duration: 2000     # 毫秒
```

| 字段 | 类型 | 必填 | 说明 |
|-------|------|----------|-------------|
| `duration` | int | ✅ | 等待的毫秒数 |

### 步骤类型：`action_batch`

执行一批动作（逻辑操作，无 I/O）。

```yaml
- id: process_results
  type: action_batch
  actions:
    - print: "Power: {{ devices.DeviceA.power }}"
    - save:
        to: constants.test_count
        value: 5
    - save:
        to: devices.DeviceA.ip
        value: "192.168.1.100"
```

所有可用动作请参见 `references/actions-catalog.md`。

### 步骤类型：`goto`

无条件跳转到另一个步骤。

```yaml
- id: skip_to_end
  type: goto
  target: final_step
```

| 字段 | 类型 | 必填 | 说明 |
|-------|------|----------|-------------|
| `target` | string | ✅ | 要跳转到的步骤 ID |
| `max_iterations` | int | ❌ | 防止无限循环的安全限制 |

---

## 常量与变量

### 常量（静态值）

```yaml
Constants:
  SSID: "MyWiFi"
  PASSWORD: "pass123"
```

在步骤字段中引用为 `{SSID}`, `{PASSWORD}`：

```yaml
send: 'AT+CWJAP="{SSID}","{PASSWORD}"'
```

### 步骤捕获（动态值）

步骤结果通过 `capture` 在步骤间传递：

```yaml
- id: get_fw
  type: serial
  send: "AT+QVERSION"
  expect: ["OK"]
  capture:
    version: "Version: (.+)"
```

在后继步骤中引用为 `{{ steps.get_fw.capture.version }}`：

```yaml
- id: check_ota
  type: http
  url: "http://ota.example.com/check?fw={{ steps.get_fw.capture.version }}"
```

### Action_batch 模板

```yaml
actions:
  - print: "当前版本: {{ steps.get_fw.capture.version }}"
  - save:
      to: devices.DeviceA.fw_ver
      value: "{{ steps.get_fw.capture.version }}"
```

### 模板变量作用域

| 语法 | 作用域 | 示例 |
|--------|-------|---------|
| `{VAR}` | 常量 | `{SSID}` |
| `{{ constants.VAR }}` | 常量（显式） | `{{ constants.SSID }}` |
| `{{ steps.ID.capture.KEY }}` | 步骤捕获 | `{{ steps.get_fw.capture.version }}` |
| `{{ devices.NAME.KEY }}` | 设备运行时数据 | `{{ devices.DeviceA.power }}` |
| `{{ session.iteration }}` | 当前循环迭代次数 | `{{ session.iteration }}` |

### 类似 Jinja 的过滤器

```yaml
if: "{{ steps.check.capture.rssi | int }} >= 20"
```

支持的过滤器：`int`, `float`, `str`, `len`, `lower`, `upper`。

---

## CLI 参考

```bash
# 执行
autocom -p dicts/pipeline.yaml          # 从文件运行
autocom -f dicts/                        # 批量运行文件夹中所有 YAML
autocom -m temps/                         # 监视文件夹，自动运行新文件

# 循环控制
-n, --iterations N                       # 最大迭代次数（别名：--loop）
--duration 30s                           # 时长限制（30s / 5m / 1h）
--infinite                                # 无限运行直到 Ctrl+C

# MCP 服务器
autocom mcp                               # stdio 模式（Claude Desktop）
autocom mcp --sse --port 8888             # SSE HTTP 模式
autocom mcp --streamable --port 8888      # Streamable HTTP 模式
autocom mcp --sse --port 8888 --auth-key s3cr3t  # 带 API 密钥

# Studio UI
autocom studio                            # 打开流水线编辑器
autocom studio --port 8080                # 在 HTTP 上启动编辑器

# REST API
autocom api                               # 启动 REST API（端口 8000）
autocom api --port 8080 --host 127.0.0.1  # 自定义端口和地址
```

---

## 输出文件

| 路径 | 内容 |
|------|---------|
| `device_logs/{timestamp}/{device}.log` | 每个设备的串口输出 |
| `device_logs/{timestamp}/EXECUTION.log` | 流水线执行日志 |
| `device_logs/{timestamp}/EXECUTION.json` | 结构化执行结果 |
| `logs/mcp_audit/{date}.jsonl` | MCP 操作审计日志 |
| `data/sessions.db` | SQLite 会话数据库 |

---

## 常见错误快速排查

| 现象 | 可能原因 | 修复 |
|---------|-------------|-----|
| 超时/无响应 | 波特率或端口错误 | 验证 COM 口和波特率 |
| 响应乱码 | 校验位/数据位不匹配 | 检查设备配置中的 `parity`、`data_bits` |
| `expect` 始终不匹配 | 响应文本与期望不同 | 先手动发送指令捕获实际响应 |
| `device not found` | 步骤引用了未定义的设备 | 检查 `Steps[*].device` 是否匹配 `Devices[*].name` |
| `goto` 目标缺失 | 目标 id 拼写错误 | 确保步骤 ID 唯一且正确 |
| `capture` 返回空 | 正则太严格或未双重转义 | 测试正则：YAML 中使用 `\\d+` 而非 `\d+` |
| 循环不结束 | `stop_on_failure: false` 且无最大迭代次数 | 添加 `--duration` 或 `-n` 限制 |