# AutoCom 配置格式规范

## 顶层结构

```yaml
ConfigForDevices: { ... }    # 设备公共配置（可选）
Devices: [ ... ]             # 设备列表（必填，至少1个）
ConfigForActions: { ... }    # Action 公共默认值（可选）
ConfigForCommands: { ... }   # 指令公共默认值（可选）
Commands: [ ... ]            # 指令序列（必填）
Constants: { ... }            # 常量/变量（可选）
```

---

## Devices（设备定义）

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| `name` | string | ✅ | 设备名称，Commands 中通过此名引用 | `"DUT_WiFi"` |
| `status` | string | ✅ | `"enabled"` / `"disabled"` | `"enabled"` |
| `port` | string | ✅ | 串口号 | `"COM66"` / `"/dev/ttyUSB0"` |
| `baud_rate` | int | ✅ | 波特率 | `115200` |
| `stop_bits` | int | ❌ | 停止位，默认 1 | `1` |
| `parity` | string | ❌ | 校验位，默认 null（无校验） | `null` / `"N"` / `"E"` / `"O"` |
| `data_bits` | int | ❌ | 数据位，默认 8 | `8` |
| `flow_control` | object | ❌ | 流控制，默认全 false | 见下方 |
| `dtr` | bool | ❌ | DTR 信号，默认 false | `false` |
| `rts` | bool | ❌ | RTS 信号，默认 false | `false` |

### flow_control 默认值

```yaml
flow_control:
  xon_xoff: false   # 软件流控
  rts_cts: false    # 硬件流控（RTS/CTS）
  dsr_dtr: false    # 硬件流控（DSR/DTR）
```

### 常用波特率参考

| 模组类型 | 常用波特率 |
|----------|-----------|
| WiFi / BLE 模组 | `115200`（默认）、`9600` |
| Cat.1 模组 | `115200` |
| 旧款 MCU | `9600`、`57600` |

---

## Commands（指令序列）

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| `command` | string | ✅ | AT 指令字符串 | `"AT+GMR"` |
| `device` | string | ✅ | 引用 Devices 中的设备 name | `"DUT_WiFi"` |
| `order` | int | ✅ | 执行顺序（数字越小越先执行） | `1` |
| `status` | string | ✅ | `"enabled"` / `"disabled"` | `"enabled"` |
| `expected_responses` | list[str] | ❌ | 期望响应关键词列表（满足任一即成功） | `["OK"]` |
| `timeout` | int | ❌ | 超时时间（毫秒），默认 2000 | `3000` |
| `concurrent_strategy` | string | ❌ | `"sequential"`（串行）/ `"parallel"`（并行），默认 sequential | `"sequential"` |
| `success_actions` | list[object] | ❌ | 成功后执行的 Action 列表 | 见 Actions 章节 |
| `error_actions` | list[object] | ❌ | 失败后执行的 Action 列表 | 见 Actions 章节 |

---

## Actions 完整参考表

| Action | 格式 | 说明 |
|--------|------|------|
| `test` | `{"test": "message"}` | 测试打印 |
| `print` | `{"print": "消息内容"}` | 打印消息 |
| `wait` | `{"wait": {"duration": 1000}}` | 等待（毫秒） |
| `retry` | `{"retry": 3}` | 重试次数 |
| `set_status` | `{"set_status": "disabled"}` | 设置当前指令状态 |
| `set_status_by_order` | `{"set_status_by_order": {"order": 2, "status": "disabled"}}` | 按 order 设置其他指令状态 |
| `execute_command` | `{"execute_command": {"command": "AT", "timeout": 1000}}` | 执行其他指令 |
| `execute_command_by_order` | `{"execute_command_by_order": 3}` | 按 order 执行其他指令 |
| `save` | `{"save": {"device": "DUT", "variable": "var1", "value": "123"}}` | 保存变量 |
| `save_conditional` | `{"save_conditional": {"device": "DUT", "variable": "csq", "pattern": "CSQ: (\\d+)"}}` | 正则提取保存 |
| `generate_random_str` | `{"generate_random_str": {"device": "DUT", "variable": "rnd", "length": 16}}` | 生成随机字符串 |
| `calculate_length` | `{"calculate_length": {"device": "DUT", "variable": "len", "data": "..."}}` | 计算字符串长度 |
| `calculate_crc` | `{"calculate_crc": {"device": "DUT", "variable": "crc", "raw_data": "..."}}` | 计算 CRC |
| `replace_str` | `{"replace_str": {"device": "DUT", "variable": "out", "data": "...", "original_str": "...", "new_str": "..."}}` | 字符串替换 |
| `wifi_connect` | `{"wifi_connect": {"ssid": "MyWiFi", "password": "Pass123", "timeout": 10}}` | 连接 WiFi |
| `get_wifi_config` | `{"get_wifi_config": {"device_ip": "192.168.1.1", "ssid": "...", "password": "..."}}` | 获取 WiFi 配置 |
| `post_wifi_config` | `{"post_wifi_config": {"device_ip": "192.168.1.1", "ssid": "...", "password": "..."}}` | 发送 WiFi 配置 |
| `get_network_page` | `{"get_network_page": {"device_ip": "192.168.1.1", "url": "/"}}` | 获取网络页面 |
| `send_file` | `{"send_file": "path/to/file.txt"}` | 发送文件到串口 |

### send_file 扩展参数

```yaml
# 默认（LF 换行，UTF-8 编码）
{"send_file": "certs/server.crt"}

# 指定换行符
{"send_file": {"path": "certs/server.crt", "line_ending": "crlf"}}
{"send_file": {"path": "certs/server.crt", "line_ending": "cr"}}

# 指定编码
{"send_file": {"path": "config.txt", "encoding": "gbk"}}

# 完整参数
{"send_file": {"path": "config.txt", "line_ending": "crlf", "encoding": "utf-8"}}
```

**line_ending 选项**：
- `lf`：LF（`\n`），Unix/Linux/Mac 默认
- `crlf`：CRLF（`\r\n`），Windows 默认
- `cr`：CR（`\r`），旧 Mac
- `none`：保持原样

---

## ConfigForDevices（设备公共配置）

所有设备共享的默认参数，设备自身可覆盖：

```yaml
ConfigForDevices:
  baud_rate: 115200
  stop_bits: 1
  data_bits: 8
  parity: null
  flow_control:
    xon_xoff: false
    rts_cts: false
    dsr_dtr: false
  dtr: false
  rts: false
```

---

## ConfigForCommands（指令公共配置）

所有指令共享的默认参数，指令自身可覆盖：

```yaml
ConfigForCommands:
  timeout: 3000
  concurrent_strategy: sequential
```

---

## ConfigForActions（Action 公共默认值）

```yaml
ConfigForActions:
  retry:
    times: 3
  wait:
    duration: 1000
```

---

## Constants（常量/变量）

```yaml
Constants:
  SSID: "TestWiFi_5G"
  PASSWORD: "TestPass123"
```

引用方式：在 `command` 中使用 `$SSID`、`$PASSWORD`。

---

## 执行命令

```bash
# 单次执行
autocom -d dicts/dict.yaml

# 循环 N 次
autocom -d dicts/dict.yaml -l 3

# 无限循环（Ctrl+C 停止）
autocom -d dicts/dict.yaml -i

# 指定配置文件
autocom -d dicts/dict.yaml -c configs/config.yaml
```

---

## 输出文件

| 文件名 | 内容 |
|--------|------|
| `{device_name}_dev_{port}_{baud_rate}.log` | 各设备串口输出日志 |
| `EXECUTION_LOG.log` | 执行总概览 |
| `*.json` | 保存的变量数据 |

---

## 常见错误排查

| 症状 | 原因 | 解决方案 |
|------|------|----------|
| 超时无响应 | 波特率不对 / 串口占用 | 确认波特率，检查 COM 口是否被占用 |
| 响应乱码 | 校验位/数据位配置错误 | 检查 `parity`、`data_bits` 是否匹配模组 |
| `device not found` | Devices 中没有该设备名 | Commands 中 `device` 字段必须精确匹配 Devices 中 `name` |
| 指令顺序乱 | 多个 `order` 相同 | 每个 Command 的 `order` 必须唯一 |
| 重试无效 | `retry` 放在 `success_actions` | `retry` 应放在 `error_actions` |
