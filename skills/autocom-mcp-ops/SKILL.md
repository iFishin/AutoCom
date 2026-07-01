---
name: autocom-mcp-ops
label: AutoCom MCP 操作
description: 管理 AutoCom MCP Server 操作——串口会话管理、流水线执行、硬件诊断和端口监控。触发关键词：打开串口/发送指令/监控端口/会话列表/流水线执行/硬件诊断/回环测试/延迟基准测试。
---

# AutoCom MCP 操作

## 用途

远程操作 AutoCom MCP Server。使用此技能管理串口会话、执行测试流水线、诊断硬件问题以及监控设备输出——全部通过 MCP 工具完成。

## 工具概览

### 流水线工具

| 工具 | 描述 |
|------|------|
| `load_pipeline` | 加载并解析 Steps 格式的 YAML/JSON 配置 |
| `validate_pipeline` | 校验配置结构和语义 |
| `run_pipeline` | 执行完整流水线（循环控制、时长、失败即停） |

### 串口基础工具

| 工具 | 描述 |
|------|------|
| `list_serial_ports` | 列出可用 COM 口及元数据 |
| `execute_serial_command` | 发送单条指令并返回响应（底层单次） |
| `monitor_serial_port` | 阻塞式串口监视，支持时长和心跳间隔 |

### 持久会话工具（推荐）

| 工具 | 描述 |
|------|------|
| `serial_session_open` | 打开持久会话（支持后台监视模式） |
| `serial_session_send` | 在会话中发送指令并等待响应 |
| `serial_session_read` | 读取会话的接收缓冲区 |
| `serial_session_close` | 关闭并清理会话 |
| `serial_session_list` | 列出所有活跃会话及统计信息 |

### 硬件诊断工具

| 工具 | 描述 |
|------|------|
| `serial_pin_status` | 读取调制解调器信号线（CTS/DSR/DCD/RI） |
| `serial_pin_set` | 设置 DTR/RTS 输出电平 |
| `serial_loopback_test` | 硬件或回声回环测试 |
| `serial_latency_bench` | 往返延迟基准测试 |

完整参数文档请参见 `references/tool-reference.md`。

## 典型工作流程

### 1. 持久会话监视

推荐用于交互式调试：

1. `serial_session_open(port="COM16", baud_rate=115200, monitor=True)` -> 获取 `session_id`
2. `serial_session_send(session_id="xxx", command="AT")` -> 快速指令响应
3. `serial_session_send(session_id="xxx", command="AT+CSQ")` -> 信号质量
4. `serial_session_read(session_id="xxx")` -> 读取缓冲的监视数据
5. `serial_session_list` -> 查看会话统计
6. `serial_session_close(session_id="xxx")` -> 清理

### 2. 流水线执行

用于自动化测试序列：

1. `load_pipeline(file_path="dicts/softap_steps.yaml")` -> 确认配置
2. `validate_pipeline(file_path="dicts/softap_steps.yaml")` -> 检查问题
3. `run_pipeline(file_path="dicts/softap_steps.yaml", loop_count=5)` -> 执行 5 轮

### 3. 硬件诊断

用于物理层故障排查：

1. `list_serial_ports` -> 找到正确的 COM 口
2. `serial_pin_status(port="COM16")` -> 检查 DSR、CTS、DCD
3. `serial_loopback_test(port="COM16", mode="hardware")` -> 验证 TX/RX 接线
4. `serial_latency_bench(port="COM16", rounds=10)` -> 测量往返时间

### 4. 快速单次指令

用于简单的"发送和读取"任务：

1. `list_serial_ports` -> 找到端口
2. `execute_serial_command(port="COM16", command="AT", baud_rate=115200)` -> 单次响应

## 会话 vs 单次：何时使用哪种方式

| 场景 | 方式 | 原因 |
|------|------|------|
| 交互式调试 | `serial_session_open/read/close` | 持久连接，后台监视 |
| 单条 AT 指令 | `execute_serial_command` | 即时发送，无需清理 |
| 长时间监视 | `serial_session_open(monitor=True)` + 定期 `read` | 后台缓冲区持续累积数据 |
| 自动化测试 | `run_pipeline` | 完整流程控制、错误处理、数据捕获 |
| 硬件问题 | `serial_pin_status/set/loopback_test/latency_bench` | 专用诊断工具 |

## 最佳实践

- 完成后始终关闭会话——调用 `serial_session_close` 释放端口
- 对于主动上报消息的设备，使用 `monitor=True`
- 会话缓冲区限制为 5000 行——定期读取以避免数据丢失
- 在循环模式运行前，先校验流水线配置
- 对延迟敏感的测量，优先使用 `execute_serial_command`（每次都新建连接）