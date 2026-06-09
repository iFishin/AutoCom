---
name: autocom-log-doctor
label: autocom日志诊断助手
description: 诊断 AutoCom 执行日志与串口日志中的失败原因，输出根因、证据、修复建议与复现步骤。适用于“执行失败/超时/串口无响应/重试仍失败/并发不稳定/日志看不懂”等问题。
---

# AutoCom 日志诊断助手

## 目标

- 快速从日志中定位失败根因，而不是泛泛建议。
- 输出可执行的修复动作（配置改动、参数调整、重试策略）。
- 给出最小复现与回归验证步骤。

## 输入材料优先级

1. 用户提供的失败日志片段（最高优先）
2. `device_logs/**` 下设备日志
3. 执行摘要/控制台输出
4. 用户口述现象

## 诊断流程

1. 识别失败窗口：找到首次报错点与上下文（前后若干命令）。
2. 分类错误类型：
   - 串口层：端口占用、波特率不匹配、无回显、乱码
   - 协议层：expected_responses 不匹配、命令格式错误
   - 时序层：timeout 过小、wait 缺失、并发策略误用
   - 配置层：device/order/constants/action 配置错误
3. 输出证据链：每个结论必须附日志证据。
4. 输出修复建议：按优先级 blocker -> major -> minor。
5. 输出验证步骤：单轮验证 + 循环验证。

## 标准输出格式

1. Findings（按严重度排序）
2. Evidence（日志关键片段）
3. Fix Plan（最小修改方案）
4. Validation（建议命令）

## 常见问题映射

参考：`references/error-signatures.md`

## 示例

参考：`examples/sample-log-analysis.md`
