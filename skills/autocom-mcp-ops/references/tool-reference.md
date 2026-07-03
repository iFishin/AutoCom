# MCP 工具参考

## 流水线工具

### load_pipeline

加载并解析 Steps 格式的配置文件。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `file_path` | string | ✅ | YAML/JSON 配置文件的路径 |
| `config_path` | string | ❌ | 独立的配置覆盖文件 |
| `config_overrides` | object | ❌ | 内联配置覆盖（合并到现有配置之上） |

返回：`devices`、`steps`、`constants`、`config_summary`

### validate_pipeline

校验配置结构和语义。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `file_path` | string | ✅ | YAML/JSON 配置文件的路径 |
| `config_path` | string | ❌ | 覆盖文件 |
| `config_overrides` | object | ❌ | 内联覆盖 |

返回：`errors`、`warnings`、`summary`

### run_pipeline

执行流水线，支持完整流程控制。

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `file_path` | string | ✅ | — | YAML/JSON 配置文件的路径 |
| `config_path` | string | ❌ | null | 覆盖文件 |
| `config_overrides` | object | ❌ | null | 内联覆盖 |
| `loop_count` | int | ❌ | null | 循环次数（CLI `-n`） |
| `duration` | string | ❌ | null | 时长限制：`"30s"`、`"5m"`、`"1h"` |
| `infinite` | bool | ❌ | false | 持续运行直到手动停止 |
| `stop_on_failure` | bool | ❌ | null | 首次失败即中止（循环模式下默认为 false） |
| `max_failures` | int | ❌ | null | 中止前允许的最大连续失败次数 |
| `interval_ms` | int | ❌ | null | 轮次之间的间隔（毫秒） |

### pipeline_list

列出指定目录下所有可用的流水线配置文件。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `base_dir` | string | ❌ | 搜索目录；默认依次查找 dicts/ 和 configs/ |

返回：`total`, `pipelines`（数组，每项包含 `file_path`, `file_name`, `relative_path`, `size_bytes`）

### pipeline_step_debug

只执行流水线中某一个步骤，方便单独调试某条指令。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `file_path` | string | ✅ | 流水线配置文件路径 |
| `step_id` | string | ✅ | 要调试的步骤 ID |
| `config_overrides` | object | ❌ | 内联配置覆盖 |

返回：`step_id`, `step_type`, `passed`, `output`, `captures`, `error`, `execution_time_ms`

### pipeline_dry_run

对流水线做干运行：解析变量、追踪控制流，但不执行实际 I/O。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `file_path` | string | ✅ | 流水线配置文件路径 |
| `config_overrides` | object | ❌ | 内联配置覆盖 |

返回：`config`, `devices`, `constants`, `steps`（含变量解析结果）, `flow_issues`, `has_issues`

---

## 执行历史分析工具

### execution_list

列出最近执行会话（从 `device_logs/` 读取）。

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `limit` | int | ❌ | 20 | 最多返回的会话数 |

返回：`total`, `sessions`（数组，每项包含 `session_id`, `path`, `has_log`, `has_json`, `device_logs`）

### execution_report

解析指定执行会话的日志和结果。

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `session_id` | string | ✅ | 会话 ID（来自 execution_list） |

返回：`session_id`, `execution_log`, `device_logs`, `summary`

### session_log_query

在指定执行会话的设备日志中搜索关键词。

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `session_id` | string | ✅ | — | 会话 ID |
| `keyword` | string | ✅ | — | 搜索关键词（大小写不敏感） |
| `max_results` | int | ❌ | 50 | 最大返回匹配数 |

返回：`session_id`, `keyword`, `total_matches`, `matches`（数组，每项包含 `file`, `line`, `text`）

---

## 串口基础工具

### list_serial_ports

无需参数。

返回：`total`、`devices`（数组，每项包含 `{name, description, hwid, manufacturer, serial_number, location, vid, pid}`）

### execute_serial_command

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `command` | string | ✅ | — | 要发送的数据 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `timeout` | number | ❌ | 5 | 响应等待时间（秒） |
| `line_ending` | string | ❌ | `0d0a` | 行结尾的十六进制字节 |
| `hex_mode` | bool | ❌ | false | 以十六进制字节发送 |
| `expected_responses` | list | ❌ | null | 期望的响应字符串 |
| `completion_rules` | object | ❌ | null | 自定义完成规则 |
| `device_name` | string | ❌ | null | 用于日志记录的设备标签 |
| `priority` | int | ❌ | 0 | 优先级级别 |

### monitor_serial_port

阻塞式串口监视器，持续推送数据。

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `duration` | number | ❌ | 10 | 监视时长（秒） |
| `heartbeat_interval` | number | ❌ | 0.3 | 进度报告间隔 |

### serial_baud_scan

自动尝试常用波特率（9600~921600），找到能收到期望响应的那个。

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `test_command` | string | ❌ | AT | 发送的测试指令 |
| `expected_response` | string | ❌ | OK | 期望收到的响应 |

返回：`port`, `total_tried`, `working_count`, `working_rates`, `results`（每项含 `baud_rate`, `success`, `response`）

### serial_hex_dump

以 hex + ASCII 格式读取串口数据，排查乱码和不可见字符问题。

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `bytes_to_read` | int | ❌ | 256 | 读取字节数 |
| `timeout` | number | ❌ | 3.0 | 等待超时（秒） |

返回：`bytes_read`, `hex_dump`（格式化 hex 行数组）, `text`（解码文本）

---

## 持久会话工具

### serial_session_open

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `data_bits` | int | ❌ | 8 | 数据位（5-8） |
| `stop_bits` | int | ❌ | 1 | 停止位（1、1.5、2） |
| `parity` | string | ❌ | none | 校验位：`none`（无）、`even`（偶校验）、`odd`（奇校验）、`mark`（标记）、`space`（空号） |
| `flow_control` | bool | ❌ | false | 启用 RTS/CTS 流控制 |
| `timeout` | number | ❌ | 5 | 读取超时（秒） |
| `label` | string | ❌ | null | 人类可读的会话标签 |
| `monitor` | bool | ❌ | false | 启用后台数据监视线程 |

返回：`session_id`、`port`、`label`、`baud_rate`、`monitor`

### serial_session_send

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `session_id` | string | ✅ | — | 来自 `open` 的会话 ID |
| `command` | string | ✅ | — | 要发送的数据 |
| `timeout` | number | ❌ | null | 响应等待覆盖值 |
| `expected_responses` | list | ❌ | null | 期望的响应字符串 |
| `line_ending` | string | ❌ | `0d0a` | 行结尾的十六进制字节 |
| `hex_mode` | bool | ❌ | false | 以十六进制字节发送 |

返回：`response`、`matched`、`elapsed_ms`

### serial_session_read

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `session_id` | string | ✅ | — | 来自 `open` 的会话 ID |
| `timeout` | number | ❌ | null | 等待数据的时间（秒） |
| `max_bytes` | int | ❌ | null | 最大读取字节数 |

返回：`data`（文本）、`bytes_count`、`session_id`

### serial_session_close

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `session_id` | string | ✅ | 要关闭的会话 ID |

返回：成功状态

### serial_session_list

无需参数。

返回：数组，每项包含 `{session_id, port, label, baud_rate, created_at, monitor, monitor_bytes, monitor_duration_seconds}`

---

## 硬件诊断工具

### serial_pin_status

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |

返回：`{cts, dsr, dcd, ri}`（布尔信号值）

### serial_pin_set

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `dtr` | bool | ❌ | null | DTR 输出电平 |
| `rts` | bool | ❌ | null | RTS 输出电平 |

### serial_loopback_test

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `mode` | string | ❌ | hardware | `hardware`（发送+读回）或 `echo`（发送+期待回复） |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `test_data` | string | ❌ | null | 硬件回环测试数据 |
| `probe_command` | string | ❌ | AT | 回声测试指令 |
| `probe_expected` | string | ❌ | OK | 期望的回声响应 |
| `timeout` | number | ❌ | 3 | 等待超时 |

返回：`success`、`sent_bytes`、`received_bytes`、`elapsed_ms`、`errors`

### serial_latency_bench

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `port` | string | ✅ | — | COM 端口名称 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `rounds` | int | ❌ | 10 | 测试轮数 |
| `test_data` | string | ❌ | AT | 每轮发送的数据 |
| `timeout` | number | ❌ | 5 | 每轮超时 |

返回：`rounds`、`send_min_ms`、`send_max_ms`、`send_avg_ms`、`first_byte_min_ms`、`first_byte_max_ms`、`first_byte_avg_ms`、`rtt_min_ms`、`rtt_max_ms`、`rtt_avg_ms`

---

## 设备参数管理工具

### device_profile_list

无需参数。

返回：`total`, `profiles`（数组，每项包含 `name`, `port`, `baud_rate`, `data_bits`, `stop_bits`, `parity`, `label`, `created`）

### device_profile_save

保存设备串口配置。之后可通过名称快速引用。

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `name` | string | ✅ | — | 配置名称（唯一标识） |
| `port` | string | ✅ | — | COM 端口名称 |
| `baud_rate` | int | ❌ | 115200 | 波特率 |
| `data_bits` | int | ❌ | 8 | 数据位 |
| `stop_bits` | int | ❌ | 1 | 停止位 |
| `parity` | string | ❌ | none | 校验位 |
| `flow_control` | bool | ❌ | false | RTS/CTS 流控 |
| `timeout` | number | ❌ | 5.0 | 读取超时（秒） |
| `label` | string | ❌ | "" | 显示标签 |

返回：`profile`（保存的配置对象）, `total`（总配置数）

### device_profile_delete

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `name` | string | ✅ | 要删除的配置名称 |

返回：`deleted`, `total`

---

## 审计日志位置

所有 MCP 工具操作均记录到：

```
logs/mcp_audit/{YYYY-MM-DD}.jsonl
```

每行是一个 JSON 对象，包含：`timestamp`（时间戳）、`tool`（工具名）、`params`（参数，已脱敏）、`success`（是否成功）、`duration_ms`（耗时毫秒）、`error`（错误信息，如有）。