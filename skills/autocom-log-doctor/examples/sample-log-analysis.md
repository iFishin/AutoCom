# 日志分析示例

## 示例 1：WiFi 连接超时

### 输入

```
[2026-07-01 09:15:00] [INFO] Pipeline started: wifi_test.yaml
[2026-07-01 09:15:01] [SEND] DeviceA -> AT
[2026-07-01 09:15:01] [RECV] DeviceA -> AT\r\nOK\r\n
[2026-07-01 09:15:01] [PASS] Step check_basic passed
[2026-07-01 09:15:02] [SEND] DeviceA -> AT+CWJAP="TestWiFi","..."
[2026-07-01 09:15:07] [WARNING] expect not matched within 5s for step connect_wifi
[2026-07-01 09:15:07] [FAIL] Step connect_wifi failed (timeout)
[2026-07-01 09:15:07] [INFO] on_error: retry(1) for step connect_wifi
[2026-07-01 09:15:08] [SEND] DeviceA -> AT+CWJAP="TestWiFi","..."
[2026-07-01 09:15:13] [WARNING] expect not matched within 5s for step connect_wifi
[2026-07-01 09:15:13] [FAIL] Step connect_wifi failed after 1 retries
```

### 输出

#### 发现

- **[阻塞级]** WiFi 连接步骤 `connect_wifi` 超时（5 秒）设置过短 — WiFi 关联 + DHCP 通常需要 8-25 秒
- **[主要级]** 首次失败后重试使用相同的过短超时，必然再次失败

#### 证据

- `check_basic` 于 09:15:01 通过（AT OK）
- `connect_wifi` 于 09:15:02 发送，期望 `["OK", "WIFI GOT IP"]`
- 两次尝试均在恰好 5 秒时超时 — 未收到任何部分响应

#### 修复方案

1. 将 `connect_wifi.timeout` 从 5 秒增大至 30 秒
2. 在连接前添加一个 2 秒的 `wait` 步骤（设备在模式切换后可能需要时间）
3. `on_error: retry(2)` 设置合理，保留不变

#### 验证

```bash
# 单次运行
autocom -p dicts/wifi_test.yaml

# 循环运行以验证稳定性（10 次）
autocom -p dicts/wifi_test.yaml -n 10
```

---

## 示例 2：期望值不匹配

### 输入

```
[2026-07-01 10:00:00] [INFO] Pipeline started: scan_test.yaml
[2026-07-01 10:00:01] [SEND] DeviceA -> AT+CWMODE=1
[2026-07-01 10:00:01] [RECV] DeviceA -> AT+CWMODE=1\r\nOK\r\n
[2026-07-01 10:00:01] [PASS] Step set_mode passed
[2026-07-01 10:00:02] [SEND] DeviceA -> AT+CWLAP
[2026-07-01 10:00:12] [RECV] DeviceA -> \r\n+CWLAP:"TestWiFi",-45,"aa:bb:cc:dd:ee:ff",1,-78\r\n\r\nOK\r\n
[2026-07-01 10:00:12] [FAIL] Step scan_ap failed — expect ['+CWLAP:'] not found in response
```

### 分析

响应中确实包含 `+CWLAP:` — 期望匹配失败的原因是字符串已被串口读取器的缓冲区处理机制消耗。实际响应被拆分到了多次读取中，而匹配逻辑仅检查当前行。

#### 发现

- **[主要级]** 尽管响应正确，`expect` 仍未匹配 — 可能是行缓冲问题
- **[次要级]** 未使用 `capture` 从多行响应中提取 AP 信息

#### 修复方案

1. 使用更宽松的期望：`["OK"]`（因为 OK 出现在最后一行）
2. 或按如下方式修改步骤：
   ```yaml
   - id: scan_ap
     type: serial
     device: DeviceA
     send: "AT+CWLAP"
     expect: ["OK"]
     capture:
       aps: 'CWLAP:"(.+?)"'
     timeout: 15
   ```

#### 验证

```bash
autocom -p dicts/scan_test.yaml
```

---

## 示例 3：控制流循环卡死

### 输入

```yaml
# 配置片段
loop: true
stop_on_failure: false

Steps:
  - id: start
    type: serial
    device: DUT
    send: "AT"
    expect: ["OK"]
    timeout: 3

  - id: loop_back
    type: goto
    target: start
```

### 日志

```
[2026-07-01 11:00:00] [PASS] Step start passed
[2026-07-01 11:00:00] [GOTO] loop_back -> start
[2026-07-01 11:00:01] [PASS] Step start passed
[2026-07-01 11:00:01] [GOTO] loop_back -> start
...（无限重复）
```

#### 发现

- **[阻塞级]** 无限循环：`goto` 跳回 `start`，未设置迭代限制且 CLI 未指定 `-n`/`--duration`

#### 修复方案

1. 添加 CLI 限制：`autocom -p loop.yaml -n 100`
2. 或为 goto 步骤添加 `max_iterations`：
   ```yaml
   - id: loop_back
     type: goto
     target: start
     max_iterations: 100
   ```

#### 验证

```bash
autocom -p loop.yaml -n 100
```

---

## 示例 4：捕获正则失败

### 输入

```
[2026-07-01 14:00:00] [SEND] DeviceA -> AT+CSQ
[2026-07-01 14:00:01] [RECV] DeviceA -> +CSQ: 22,99\r\n\r\nOK\r\n
[2026-07-01 14:00:01] [PASS] Step get_csq passed
...
[2026-07-01 14:00:05] Step print_signal uses capture variable rssi but it is empty
```

#### 分析

配置为：`capture: { rssi: '\d+' }` — 正则 `\d+` 匹配数字，但会匹配*任意位置*的数字，并未锚定到 `CSQ:` 后面的值。实际响应为 `+CSQ: 22,99`，裸的 `\d+` 可能匹配到 `22`、`99` 甚至仅 `2`，具体取决于实现。

#### 发现

- **[主要级]** 捕获正则 `\d+` 存在歧义，可能匹配到错误的值
- 在 YAML 中，单反斜杠 `\d` 还可能被解释为转义序列

#### 修复方案

使用锚定捕获并双重转义正则：

```yaml
capture:
  rssi: '\\+CSQ: (\\d+)'
```

#### 验证

```bash
autocom -p dicts/csq_test.yaml
```