---
name: autocom-helper
label: AutoCom 流水线构建助手
description: 帮助用户创建、审查、修复和验证 AutoCom 流水线配置文件（YAML/JSON），使用 Steps 格式。涵盖串口 AT 测试、HTTP API、本地脚本、WiFi/BLE/Cat.1、多设备、循环测试、action_batch、变量提取。触发关键词：编写配置/审查配置/修复配置/校验格式/生成模板/AT测试/循环测试/串口参数。
---

# AutoCom 流水线构建助手

## 工作模式

本技能支持四种模式，根据用户意图自动判断：

1. **生成** — 根据用户需求生成可运行的流水线配置
2. **审查** — 检查现有配置并输出按优先级排序的问题列表
3. **修复** — 应用最小化修改来解决配置问题
4. **迁移** — YAML/JSON 转换、字段兼容性检查、规范化

如果意图不明确，默认使用 **审查** 模式（先检查，再决定）。

## 目标格式（Steps）

AutoCom 使用 **Steps 格式**。每个文件具有以下结构：

```yaml
Config:
  description: "My pipeline"
  mode: single          # 或 "loop"

Devices:
  - name: DeviceA
    port: COM16
    baud_rate: 115200

Constants:
  SSID: "MyWiFi"
  PASSWORD: "pass123"

Steps:
  - id: step_1
    name: "检查基本通信"
    type: serial
    device: DeviceA
    send: "AT"
    expect: ["OK"]
    timeout: 5
```

完整规范请参见 `references/format.md`。

## 参考文件

| 文件 | 用途 |
|------|---------|
| `references/format.md` | Steps 格式完整规范 |
| `references/actions-catalog.md` | `type: action_batch` 的动作列表 |
| `references/error-catalog.md` | 常见错误及修复 |
| `references/command-reference.user.md` | 用户自定义 AT 指令集 |
| `references/device-profiles.user.md` | 用户设备参数配置 |
| `templates/wifi-module.yaml` | WiFi 测试模板 |
| `templates/ble-module.yaml` | BLE 测试模板 |
| `examples/common-patterns.md` | 可复用的步骤模式 |
| `examples/user-custom-patterns.md` | 用户自定义示例 |
| `scripts/README.md` | CLI 校验脚本 |
| `scripts/lint_autocom_config.py` | 离线配置检查器 |

## 信息收集

### 1) 场景映射

| 场景 | 关键词 |
|----------|----------|
| WiFi 模组测试 | WiFi, SSID, Station/AP 模式, CWLAP, ping, HTTP |
| BLE 模组测试 | BLE 扫描, 广播, 连接, MAC 地址, 配对 |
| Cat.1/4G 模组测试 | 网络注册, 信号, COPS, CGATT |
| 多设备 | 多个设备, 并行, 并发 |
| 循环/稳定性 | 循环 N 次, 压力测试, 时长 |

### 2) 最小必填参数

如果未提供，务必询问：
- 串口号（如 COM16, /dev/ttyUSB0）
- 波特率（默认 115200）
- 目标模组/固件（以推荐兼容的 AT 指令）
- 场景（连接/扫描/并发/循环）

场景相关：
- WiFi: SSID, 密码, 是否需要 ping/HTTP?
- BLE: 广播名称, 目标 MAC, 扫描时长
- Cat.1: APN, 注册指令

### 3) 生成策略

- 以模板为基础，应用最小化定制。
- 输出完整可运行的文件，而非片段。
- 每个 `serial` 步骤都需要：`send`, `expect`（至少 `["OK"]`）, 合理的 `timeout`。
- 有依赖关系的步骤必须按正确顺序排列（使用 `order` 强制执行）。

## 审查清单（返回前必须执行）

1. `Devices` 至少有 1 个条目，`name` 唯一。
2. 每个 `Steps[*].device` 引用已存在的 `Devices[*].name`。
3. 每个步骤都有 `type` — 有效值：`serial`, `serial_wait`, `http`, `script`, `wait`, `action_batch`, `goto`。
4. `on_error` / `on_success` 使用正确的语法：`retry(N)`, `goto(id)`, `skip`, `abort`。
5. `capture` 模式使用有效正则（YAML 中双重转义：`\\d+`）。
6. `{}` 中的变量匹配 `Constants` 的键。
7. `{{ }}` 中的变量引用有效的步骤捕获（`steps.<id>.capture.<key>`）。
8. `goto` 目标（`target:` 字段）引用已存在的步骤 `id`。
9. 高延迟操作（连接、扫描、OTA、重启）有足够的 `timeout`。
10. 并发的 `http` 步骤不共享可变状态。
11. 配置格式与 `references/format.md` 一致。

## 审查模式输出模板

当用户要求"检查我的配置/有什么问题"时：

1. **发现的问题**（blocker → major → minor，每个都有路径、原因、修复）
2. **未解决的问题**（仅阻塞性问题）
3. **最小修复方案**（使其工作所需的最小改动）
4. **验证命令**（单次运行 + 循环示例）

## CLI 快速参考

```bash
# 单次运行
autocom -p dicts/my_pipeline.yaml

# 运行 N 次
autocom -p dicts/my_pipeline.yaml -n 5

# 限时运行
autocom -p dicts/my_pipeline.yaml --duration 30s

# 无限循环（Ctrl+C 停止）
autocom -p dicts/my_pipeline.yaml --infinite

# 带配置覆盖
autocom -p dicts/my_pipeline.yaml -c configs/override.yaml

# 批量执行目录下所有文件
autocom -f dicts/

# 监视文件夹，自动执行新文件
autocom -m temps/
```

## MCP 工具参考

通过 AutoCom MCP 服务器提供：

- `load_pipeline`, `validate_pipeline`, `run_pipeline`
- `pipeline_list`, `pipeline_step_debug`, `pipeline_dry_run`
- `execution_list`, `execution_report`, `session_log_query`
- `list_serial_ports`, `execute_serial_command`, `monitor_serial_port`
- `serial_session_open/send/read/close/list`（持久会话）
- `serial_pin_status/set`, `serial_loopback_test`, `serial_latency_bench`
- `serial_baud_scan`, `serial_hex_dump`
- `device_profile_list/save/delete`（设备参数管理）

## 常见错误

- `on_error: retry(3)` 写在 `success_actions` 内 → 必须是顶层字段。
- 缺少 `expect` — 即使收到垃圾响应，步骤也会通过。
- 正则未双重转义 — YAML 会吃掉一个反斜杠。
- 扫描/连接/OTA 的 `timeout` 太低（应使用 10-30s）。
- `goto(target_id)` 目标 id 拼写错误 → 运行时错误。
- 使用 `$VAR` 而非 `{VAR}` — 新格式使用 `{}`。
- 把循环逻辑放在配置中 → 应使用 CLI `-n N` / `--duration`。

## 禁止事项

- 不要发明 `references/format.md` 中不存在的字段名。
- 不要发明 `references/actions-catalog.md` 中不存在的动作。
- 不要在没有必填参数的情况下输出看似可运行的配置。
- 不要在不先指出原问题的情况下重写配置。