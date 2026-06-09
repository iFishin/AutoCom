# AutoCom 配置常见错误目录

本文件用于审查/修复模式下的错误映射，帮助快速定位并给出稳定修复建议。

## E001 设备名不匹配

- 症状: command.device 在 Devices 中不存在
- 严重级别: blocker
- 典型原因: 拼写不一致、复制后未同步修改
- 修复建议: 统一 Devices.name 与 Commands[*].device

## E002 order 冲突或乱序

- 症状: order 重复、跨段混乱、依赖关系错位
- 严重级别: major
- 典型原因: 插入命令后未重排
- 修复建议: 按执行依赖重排 order，并保持唯一

## E003 expected_responses 缺失/不合理

- 症状: 命令执行后误判成功或失败
- 严重级别: major
- 典型原因: 没填响应、响应关键词与固件输出不匹配
- 修复建议: 依据实际模组回显补充 expected_responses

## E004 timeout 过小

- 症状: 扫描、联网、HTTP 命令频繁超时
- 严重级别: major
- 典型原因: 沿用默认 1~3 秒
- 修复建议: 对耗时命令提升 timeout，并加 error_actions.retry

## E005 retry 放置错误

- 症状: 失败不重试或逻辑异常
- 严重级别: major
- 典型原因: 把 retry 写到 success_actions
- 修复建议: retry 放到 error_actions

## E006 变量未定义

- 症状: 命令中出现 $VAR 但 Constants 未定义
- 严重级别: blocker
- 典型原因: 变量命名改动后漏改
- 修复建议: 增补 Constants 或改回已有变量名

## E007 并发策略误用

- 症状: 命令链时序错乱、结果不稳定
- 严重级别: major
- 典型原因: 依赖链使用 parallel
- 修复建议: 依赖链改为 sequential；仅独立命令并行

## E008 Action 未注册

- 症状: 运行时报 unknown action
- 严重级别: blocker
- 典型原因: 使用了未定义 action 或拼写错误
- 修复建议: 对照 docs/Actions.md 更正 action 名称与参数结构

## E009 串口参数不兼容

- 症状: 无响应、乱码、偶发失败
- 严重级别: major
- 典型原因: baud_rate/parity/data_bits 与设备实际不一致
- 修复建议: 按设备规格调整 ConfigForDevices/Devices 字段

## E010 只给 Commands 片段

- 症状: 用户拿到配置无法直接执行
- 严重级别: minor
- 典型原因: 输出未包含 Devices/ConfigForCommands
- 修复建议: 默认提供完整可运行文件，片段仅在用户明确要求时提供
