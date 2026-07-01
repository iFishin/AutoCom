# Action Batch 动作目录

以下所有动作均可用于 `type: action_batch` 步骤的 `actions:` 列表中。

## Print（打印）

向日志输出一条消息。

```yaml
- print: "Pipeline step completed"
```

支持模板变量：

```yaml
- print: "当前版本: {{ steps.check_fw.capture.version }}"
- print: "SSID: {SSID}"
```

---

## Wait（等待）

暂停执行一段时间。

```yaml
- wait:
    duration: 1000     # 毫秒
```

---

## Save（保存）

在运行时上下文中存储一个值。

```yaml
- save:
    to: constants.my_var
    value: "hello"

- save:
    to: devices.DeviceA.power
    value: 100

- save:
    to: devices.DeviceA.fw_version
    value: "{{ steps.check_fw.capture.version }}"
```

| 字段 | 必填 | 说明 |
|-------|----------|-------------|
| `to` | ✅ | 目标路径：`constants.KEY`、`devices.NAME.KEY`、`steps.ID.capture.KEY` |
| `value` | ✅ | 值（支持模板变量） |

---

## Retry（重试）

失败时重试当前 action_batch 块。

```yaml
- retry: 3
```

注意：这只会重试 action_batch 本身，不会重试单个串口指令。
对于串口步骤的重试，请使用顶层 `on_error: retry(N)`。

---

## Generate Random String（生成随机字符串）

```yaml
- generate_random_str:
    to: constants.token         # 存储位置
    length: 16                  # 字符串长度
```

---

## Calculate Length（计算长度）

```yaml
- calculate_length:
    to: constants.data_len
    data: "{{ steps.get_fw.capture.version }}"
```

---

## Calculate CRC（计算 CRC 校验）

```yaml
- calculate_crc:
    to: constants.checksum
    raw_data: "some data"
```

---

## Replace String（替换字符串）

```yaml
- replace_str:
    to: constants.fixed
    data: "a-b-c"
    original_str: "-"
    new_str: "_"
```

---

## WiFi Connect（WiFi 连接）

将主机连接到 WiFi 网络（使用 pywifi）。

```yaml
- wifi_connect:
    ssid: "{SSID}"
    password: "{PASSWORD}"
    timeout: 20           # 每次尝试的超时秒数（默认 10）
    retry: 3              # 尝试次数（默认 3）
    retry_interval: 1.0   # 尝试间隔秒数
    iface_index: 0        # WiFi 接口索引
```

---

## Post WiFi Config（发送 WiFi 配置）

通过 HTTP POST 向设备发送 WiFi 凭据（SoftAP 配置）。

```yaml
- post_wifi_config_once:
    device_ip: "192.168.1.1"
    ssid: "{Target_SSID}"
    password: "{Target_PASSWORD}"
    timeout: 5
    repeat: 3             # 发送次数（服务器可能不响应）
    repeat_interval: 0.5  # 发送间隔秒数
```

---

## Get WiFi Config（获取 WiFi 配置）

通过 HTTP GET 向设备发送 WiFi 凭据（SoftAP 配置）。

```yaml
- get_wifi_config_once:
    device_ip: "192.168.1.1"
    ssid: "{Target_SSID}"
    password: "{Target_PASSWORD}"
    timeout: 5
    repeat: 3
    repeat_interval: 0.5
```

---

## Get Network Page（获取网络页面）

通过 HTTP GET 从设备获取页面。

```yaml
- get_network_page:
    device_ip: "192.168.1.1"
    url: "/"
```

---

## Send File（发送文件）

通过串口发送文件内容。

```yaml
- send_file: "certs/server.crt"

# 带选项：
- send_file:
    path: "config.txt"
    encoding: "utf-8"       # 或 "gbk"、"latin-1"
    line_ending: "lf"       # "lf"、"crlf"、"cr"、"none"
```