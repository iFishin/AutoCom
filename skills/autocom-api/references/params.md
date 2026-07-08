# 参数参考

## 串口操作

### POST /api/ports/{port}/command

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | path | string | ✅ | — | 串口号，如 COM16 |
| command | query | string | ✅ | — | 要发送的指令 |
| baud_rate | query | int | ❌ | 115200 | 波特率 |
| timeout | query | float | ❌ | 5.0 | 等待响应超时（秒） |
| line_ending | query | string | ❌ | 0d0a | 结尾符的十六进制 |
| hex_mode | query | bool | ❌ | false | 是否以 hex 发送 |

### POST /api/ports/{port}/baud-scan

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | path | string | ✅ | — | 串口号 |
| test_command | body | string | ❌ | "AT" | 测试指令 |
| expected_response | body | string | ❌ | "OK" | 期望收到的内容 |
| line_ending | body | string | ❌ | "0d0a" | 结尾符 |

请求体为 JSON：`{"test_command": "AT", "expected_response": "OK"}`

### GET /api/ports/{port}/hex-dump

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | path | string | ✅ | — | 串口号 |
| baud_rate | query | int | ❌ | 115200 | 波特率 |
| bytes_to_read | query | int | ❌ | 256 | 读取字节数 |
| timeout | query | float | ❌ | 3.0 | 超时（秒） |

### GET /api/ports/{port}/pin-status

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | path | string | ✅ | — | 串口号 |
| baud_rate | query | int | ❌ | 115200 | 波特率 |

### POST /api/ports/{port}/pin-set

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | path | string | ✅ | — | 串口号 |
| dtr | query | bool | ❌ | null | true=高电平 false=低电平 |
| rts | query | bool | ❌ | null | true=高电平 false=低电平 |
| baud_rate | query | int | ❌ | 115200 | 波特率 |

### POST /api/ports/{port}/loopback

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | path | string | ✅ | — | 串口号 |
| mode | query | string | ❌ | hardware | hardware 或 echo |
| baud_rate | query | int | ❌ | 115200 | 波特率 |
| test_data | query | string | ❌ | null | 硬件回环测试数据 |
| probe_command | query | string | ❌ | AT | 回声测试指令 |
| probe_expected | query | string | ❌ | OK | 期望响应 |
| timeout | query | float | ❌ | 3.0 | 超时（秒） |

### POST /api/ports/{port}/latency

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | path | string | ✅ | — | 串口号 |
| baud_rate | query | int | ❌ | 115200 | 波特率 |
| rounds | query | int | ❌ | 10 | 测试轮数 |
| test_data | query | string | ❌ | AT | 测试数据 |
| timeout | query | float | ❌ | 5.0 | 每轮超时（秒） |

---

## 持久会话

### POST /api/sessions

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| port | query | string | ✅ | — | 串口号 |
| baud_rate | query | int | ❌ | 115200 | 波特率 |
| timeout | query | float | ❌ | 5.0 | 读取超时 |
| label | query | string | ❌ | null | 会话标签 |

### POST /api/sessions/{id}/send

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| session_id | path | string | ✅ | — | 会话 ID |
| command | query | string | ✅ | — | 要发送的指令 |
| timeout | query | float | ❌ | null | 响应超时覆盖 |
| line_ending | query | string | ❌ | 0d0a | 结尾符 |

### POST /api/sessions/{id}/read

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| session_id | path | string | ✅ | — | 会话 ID |
| timeout | query | float | ❌ | null | 等待超时 |
| max_bytes | query | int | ❌ | null | 最大读取字节数 |

---

## 设备配置

### POST /api/profiles

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| name | query | string | ✅ | — | 配置名称（唯一） |
| port | query | string | ✅ | — | COM 端口 |
| baud_rate | query | int | ❌ | 115200 | 波特率 |
| data_bits | query | int | ❌ | 8 | 数据位 |
| stop_bits | query | int | ❌ | 1 | 停止位 |
| parity | query | string | ❌ | none | none/even/odd/mark/space |
| flow_control | query | bool | ❌ | false | RTS/CTS 流控 |
| timeout | query | float | ❌ | 5.0 | 超时 |
| label | query | string | ❌ | "" | 显示标签 |

---

## 流水线

### POST /api/pipeline/validate

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| file_path | query | string | ✅ | — | 配置文件路径 |
| config_path | query | string | ❌ | null | 覆盖文件 |
| config_overrides | query | string | ❌ | null | JSON 格式覆盖 |

### POST /api/pipeline/run

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| file_path | query | string | ✅ | — | 配置文件路径 |
| loop_count | query | int | ❌ | null | 循环轮数 |
| duration | query | string | ❌ | null | 限时 30s/5m/1h |
| stop_on_failure | query | bool | ❌ | null | 失败即停 |
| config_overrides | query | string | ❌ | null | JSON 覆盖 |

### POST /api/pipeline/dry-run

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| file_path | query | string | ✅ | — | 配置文件路径 |
| config_overrides | query | string | ❌ | null | JSON 覆盖 |

### POST /api/pipeline/step-debug

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| file_path | query | string | ✅ | — | 配置文件路径 |
| step_id | query | string | ✅ | — | 要调试的步骤 ID |
| config_overrides | query | string | ❌ | null | JSON 覆盖 |