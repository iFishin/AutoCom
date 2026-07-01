---
name: autocom-log-doctor
label: AutoCom 日志诊断助手
description: 诊断 AutoCom 执行日志与串口日志中的失败原因，输出根因、证据、修复建议与验证步骤。适配 PipelineScheduler 步骤级输出、Logger 格式化日志、多设备会话跟踪。触发关键词：日志分析/诊断失败/调试超时/步骤失败/分析崩溃/重试耗尽/期望不匹配。
---

# AutoCom 日志诊断助手

## 目标

- 快速从日志中定位失败根因，而非泛泛建议。
- 输出可执行的修复动作（配置修改、参数调整、重试策略）。
- 给出最小复现与回归验证步骤。

## 日志来源（按优先级排序）

1. **用户提供的失败日志片段**（最高优先）
2. **执行日志**：`device_logs/{session_timestamp}/EXECUTION.log` — 步骤级执行跟踪
3. **设备串口日志**：`device_logs/{session_timestamp}/{device_name}.log` — 每个设备的原始串口 I/O
4. **MCP 审计日志**：`logs/mcp_audit/{date}.jsonl` — MCP 工具操作的 JSON Lines 审计
5. **控制台输出** — 用户口述的 CLI 行为

### Logger 输出格式

```
[2026-07-01 14:30:00] [INFO] Pipeline started: wifi_test.yaml
[2026-07-01 14:30:01] [SEND] DeviceA -> AT
[2026-07-01 14:30:01] [RECV] DeviceA -> AT\r\nOK\r\n
[2026-07-01 14:30:01] [PASS] Step check_basic passed
[2026-07-01 14:30:02] [SEND] DeviceA -> AT+CWJAP="TestWiFi","..."
[2026-07-01 14:30:17] [FAIL] Step connect_wifi failed (timeout)
```

日志级别：`TRACE`, `DEBUG`, `INFO`, `PASS`, `WARNING`, `FAIL`, `ERROR`, `FATAL`

## 诊断流程

1. **定位失败窗口**：找到第一个错误/FAIL 条目及其前后上下文（3-5 个前置步骤）。
2. **分类错误类型**：
   - **串口层**：端口占用、波特率不匹配、无回显、乱码
   - **期望匹配层**：`expect` 字符串未在响应中找到、响应被截断、时序竞争
   - **捕获层**：正则未匹配、捕获变量为空
   - **控制流**：`on_error` 重试耗尽、`goto` 目标未找到、`if` 条件评估错误
   - **配置层**：`device` 引用缺失、`type` 无效、常量未定义
3. **输出证据链**：每个结论必须引用日志行。
4. **输出修复方案**：按 blocker → major → minor 优先级排序。
5. **输出验证**：单次运行命令 + 循环运行命令。

## 标准输出格式

1. **发现的问题**（按严重度排序）
2. **证据**（带时间戳的关键日志片段）
3. **修复方案**（最小配置修改）
4. **验证**（建议的命令）

## 常见错误签名

参考：`references/error-signatures.md`

## 示例

参考：`examples/sample-log-analysis.md`

## CLI 复现命令

```bash
# 单次运行复现
autocom -p dicts/pipeline.yaml

# 循环运行验证修复
autocom -p dicts/pipeline.yaml -n 10

# 限时压力测试
autocom -p dicts/pipeline.yaml --duration 30s
```