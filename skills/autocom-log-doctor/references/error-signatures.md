# 常见日志签名与根因映射

## L001 timeout waiting response

- 现象: 指令超时，无期望响应
- 常见根因:
  - timeout 设置过短
  - 波特率/串口参数不匹配
  - 指令前置条件未满足
- 建议:
  - 提升 timeout
  - 校验 port/baud_rate/parity/data_bits
  - 在关键步骤前补 wait

## L002 device not found

- 现象: 命令执行时报 device not found
- 根因: Commands.device 与 Devices.name 不一致
- 建议: 统一命名，避免复制后漏改

## L003 unknown action

- 现象: 执行 action 报 unknown action
- 根因: action 拼写错误或未注册
- 建议: 检查 action 名称与参数结构

## L004 garbled output / decode issues

- 现象: 日志乱码、响应不可读
- 根因: 串口参数不匹配、设备输出非 UTF-8
- 建议: 调整串口参数；必要时用 hex 方式分析

## L005 flaky in parallel mode

- 现象: 并发模式下偶发失败
- 根因: 命令存在依赖关系却被并行执行
- 建议: 依赖链改为 sequential；并发仅用于独立命令
