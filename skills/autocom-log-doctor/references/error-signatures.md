# 常见日志签名与根因映射

## L001：步骤超时 / 未收到期望响应

- **日志签名**：`[FAIL] Step <id> failed (timeout)` 和 `[WARNING] expect not matched within <N>s`
- **常见根因**：
  - `timeout` 设置过短（WiFi 连接：30s+，OTA：60s+）
  - 波特率/串口参数不匹配
  - 设备未处于预期状态（前置步骤被跳过）
  - 设备未收到命令（DTR/RTS 或接线问题）
- **证据检查点**：
  1. `[SEND]` 行是否正确发出？
  2. 是否有任何 `[RECV]` 数据？
  3. 设备历史响应时间是多长？
- **修复方案**：
  - 增大该步骤的 `timeout`（秒）
  - 验证串口参数与设备配置一致
  - 在高延迟操作前添加 `wait` 步骤
  - 为偶发故障添加 `on_error: retry(N)`

---

## L002：期望字符串未匹配

- **日志签名**：`[FAIL] Step <id> failed` — expect `['OK']` not found in response
- **常见根因**：
  - `expect` 字符串与实际设备输出不匹配
  - 响应包含额外字符（空格、\r\n 差异）
  - 设备返回了错误消息而非 OK
- **证据检查点**：
  1. 对比 `[SEND]` 和 `[RECV]` 行——设备是否回复了？
  2. 响应中是否包含期望的字符串或不同的内容？
  3. 固件是否已更改（不同的响应格式）？
- **修复方案**：
  - 先手动发送命令以捕获实际响应
  - 使用更宽松的 `expect` 匹配（但不要太宽松）
  - 从期望字符串中去除末尾的 `\r\n`

---

## L003：`capture` 正则未提取数据

- **日志签名**：后续步骤中捕获变量为空/null
- **常见根因**：
  - 正则太严格或 YAML 中未双重转义
  - 固件版本更新后设备输出格式已更改
  - `capture` 键针对经过 `expect` 过滤后的响应进行匹配
- **证据检查点**：
  1. 查看 `[RECV]` 行——设备实际返回了什么？
  2. 测试正则：`re.search(pattern, raw_response)` 是否产生匹配？
- **修复方案**：
  - 针对实际设备输出测试正则
  - YAML 中双重转义反斜杠：使用 `\\d+` 而非 `\d+`
  - 使用非贪婪 `(.+?)` 而非贪婪 `(.+)`

---

## L004：`on_error` 重试耗尽

- **日志签名**：`[WARNING] on_error retry(3) exhausted for step <id>` 和 `[FAIL] Step <id> failed after <N> retries`
- **常见根因**：
  - 根本问题是持久性（非偶发），重试无济于事
  - 该操作的超时时间太小
  - 设备处于不良状态（需要断电或硬件复位）
- **证据检查点**：
  1. 所有 N 次尝试是否以相同方式失败？（每次都是相同错误？）
  2. 重试之间的间隔是多少？
  3. 是否有硬件条件（DTR 切换、掉电）？
- **修复方案**：
  - 修复根本原因而非重试
  - 对于真正的偶发操作，增加超时时间
  - 考虑 `on_error: skip`（忽略）或 `on_error: goto(...)`（替代流程）

---

## L005：`device` 未找到

- **日志签名**：`[ERROR] device 'XYZ' not found in Devices list`
- **根因**：步骤的 `device` 字段不匹配任何 `Devices[*].name`
- **修复方案**：
  - 确保步骤设备名称与设备条目名称完全一致
  - 检查末尾空格或不可见字符

---

## L006：`goto` 目标不存在

- **日志签名**：`[ERROR] goto target 'XYZ' not found among step ids`
- **常见根因**：目标步骤 id 拼写错误、已删除或从未定义
- **修复方案**：
  - 验证所有 `goto(id)`、`on_error: goto(id)`、`on_success: goto(id)` 和 `target:` 引用

---

## L007：输出乱码 / 解码失败

- **日志签名**：`[WARNING] decode failed at position <N>`，响应显示不可读字符
- **常见根因**：
  - 波特率/校验位/数据位/停止位不匹配
  - 设备输出非 UTF-8 编码（GBK、Latin-1、二进制）
  - 流控配置错误（RTS/CTS 不匹配）
- **证据检查点**：
  1. 原始十六进制数据是否显示有效的帧结构？
  2. 尝试对相同数据使用不同编码
- **修复方案**：
  - 根据设备数据手册验证串口参数
  - 使用 `hex_mode` 发送/接收原始字节

---

## L008：串口端口忙 / 访问被拒绝

- **日志签名**：`[ERROR] SerialException: could not open port <port>` 或 `Access is denied`
- **常见根因**：
  - 端口已在其他工具中打开（MCP 会话、IDE 串口监视器等）
  - 权限不足
- **修复方案**：
  - 关闭同一端口的其他连接
  - 使用 `serial_session_list` 检查是否有残留的 MCP 会话

---

## L009：`if` / `unless` 条件评估错误

- **日志签名**：步骤在条件满足时意外跳过
- **常见根因**：
  - 模板变量未解析（空的 `{{ }}` 引用）
  - 比较运算符或类型不匹配
  - 未使用类似 Jinja 的过滤器（数值比较需要 `| int`）
- **修复方案**：
  - 验证引用的捕获变量有值
  - 使用显式过滤器：`{{ steps.x.capture.y | int }} >= 20`

---

## L010：循环永不终止

- **日志签名**：流水线无限运行没有进展
- **常见根因**：
  - `stop_on_failure: false` + 无迭代/时长限制
  - 基于 goto 的循环未设置 `max_iterations`
  - 条件始终评估为 `if: true`
- **修复方案**：
  - 始终从 CLI 传递 `-n N` 或 `--duration`
  - 为 `goto` 循环添加 `max_iterations`

---

## L011：MCP 会话监视数据未被读取

- **日志签名**：`monitor_buffer` 持续增长（可在 `serial_session_list` 中查看）
- **常见根因**：以 `monitor=True` 打开会话但从未调用 `serial_session_read`
- **修复方案**：
  - 定期调用 `serial_session_read(session_id)` 来清空缓冲区
  - 缓冲区最多 5000 行；旧数据会被丢弃

---

## L012：MCP 审计：操作失败

- **日志签名**（在 `logs/mcp_audit/{date}.jsonl` 中）：`"success": false` 附带错误详情
- **常见根因**：
  - 传递给 MCP 工具的参数无效
  - 执行时串口端口不可用
  - 流水线文件路径无效或格式错误
- **修复方案**：
  - 检查工具参数是否符合预期类型
  - 在调用设备相关工具前验证端口可用性