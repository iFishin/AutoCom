---
name: autocom-helper
label: autocom配置助手
description: 帮助用户快速编写、修复、校验 AutoCom 执行配置文件（YAML/JSON）。适用于 WiFi/BLE/Cat.1 AT 测试、多设备并发、循环稳定性测试、Action 编排、变量提取。用户表达“写配置/改配置/修配置/检查格式/生成模板/AT 测试用例/并发测试/循环测试/串口参数填写”时触发。
---

# AutoCom 配置助手

## 工作模式

本 skill 必须支持并自动识别以下四种模式：

1. 生成模式：从需求生成可直接执行的完整配置文件。
2. 审查模式：检查用户现有配置并输出问题清单（按严重级别排序）。
3. 修复模式：针对已有报错或审查结果给最小修改补丁。
4. 迁移模式：JSON/YAML 双向转换、字段兼容修正、旧配置规范化。

若用户意图不明确，优先进入审查模式（先找问题，再决定是否重写）。

## 目标

- 生成可直接运行的 AutoCom 配置（不是演示片段）。
- 优先减少用户二次修改成本：端口、波特率、关键命令、超时、重试、日志提示一次到位。
- 输出前做结构与语义校验，避免常见运行期错误（device 不匹配、order 冲突、超时不合理等）。

## 项目约束（必须遵守）

1. 结构字段以项目既有规范为准：`ConfigForDevices / Devices / ConfigForCommands / Commands / Constants`。
2. Action 能力以本目录文档为准，不编造新 action：`references/actions-catalog.md`。
3. 格式规则和模板优先使用本 skill 目录下文件：
   - `references/format.md`

- `references/actions-catalog.md`
- `references/command-reference.user.md`
- `references/device-profiles.user.md`
- `templates/wifi-module.yaml`
- `templates/ble-module.yaml`
- `examples/common-patterns.md`
- `examples/user-custom-patterns.md`

4. 若用户提供了自定义 AT 指令文档，优先参考 `references/command-reference.user.md`。
5. 如与历史记忆冲突，以仓库中的最新文件为准。
6. 若信息不足，先补问最少必要参数；不要盲猜端口、SSID、密码等关键值。
7. 不输出真实敏感信息（密码、鉴权 key）；示例中使用占位值。

## 事实来源优先级

出现冲突时按以下优先级取值：

1. 用户在本目录补充的参考文件（`references/command-reference.user.md`、`references/device-profiles.user.md`、`examples/user-custom-patterns.md`）
2. 本 skill 内规范文件（`references/format.md`、`references/actions-catalog.md`、`references/error-catalog.md`）
3. 本 skill 内模板与示例（`templates/*`、`examples/common-patterns.md`）
4. 历史经验（仅兜底，且须标注不确定）

## 信息收集流程

### 1) 识别场景

根据用户请求映射到场景：

| 场景           | 特征关键词                                          |
| -------------- | --------------------------------------------------- |
| WiFi 模组测试  | WiFi 连接、SSID、Station/AP 模式、CWLAP、Ping、HTTP |
| BLE 模组测试   | BLE 广播、扫描、连接、MAC 地址、配对                |
| Cat.1 模组测试 | 4G、模组重启、信号、注册网络                        |
| 多设备并发测试 | 多个设备、并行、同时                                |
| 压力/循环测试  | 循环 N 次、压力测试、稳定性                         |

### 2) 最小必填参数

未提供时必须追问：

- 串口号（例如 COM66）
- 波特率（默认 115200）
- 目标模组/固件指令集（避免输出不兼容 AT 指令）
- 目标场景（连接/扫描/并发/循环/稳定性）

按场景补充：

- WiFi：SSID、密码、是否需要 Ping/HTTP
- BLE：广播名、目标 MAC、扫描时长
- Cat.1：网络注册/信号/拨号相关命令

### 3) 生成策略

- 优先使用现成模板，再做最小差异修改。
- 一次性给出完整文件，不只给 Commands 片段（除非用户明确只要片段）。
- `expected_responses`、`timeout`、`error_actions` 必须给出。
- 连续依赖型步骤（如设置模式 -> 等待 -> 连接）要补 `wait`。

### 4) 诊断策略（审查/修复模式）

- 先输出问题，再输出修改建议。
- 问题按严重级别排序：
  - blocker：无法执行或高概率立即失败
  - major：可执行但高概率行为错误
  - minor：可执行但可维护性或稳定性差
- 每个问题必须包含：
  - 位置（路径 + 字段/命令 order）
  - 原因
  - 修复方式
  - 修复后片段（必要时）

## 输出前校验清单（必须执行）

1. `Devices` 至少 1 个，且 `name` 唯一。
2. 每条 `Commands[*].device` 都能在 `Devices.name` 中找到。
3. `order` 唯一且连续可读。
4. 高耗时命令设置足够 `timeout`（如联网、扫描、HTTP）。
5. `error_actions` 至少包含 `retry` 或明确失败提示。
6. 变量引用（`$VAR`）都在 `Constants` 中定义。
7. `expected_responses` 非空且与命令语义一致。
8. `concurrent_strategy` 与场景匹配（依赖链命令禁用并行）。
9. 配置格式与项目文档一致，可直接 `autocom -d <file>` 运行。

## 三层校验流程（增强健壮性）

1. 结构层：键名、类型、必填项、枚举值、字段拼写。
2. 语义层：设备映射、执行顺序、变量引用、Action 放置位置。
3. 运行层：给出最小执行命令与预期行为，必要时建议先跑单轮再压测。

若用户请求“检查配置问题”，输出必须显式区分这三层结论。

## 标准输出协议

默认输出：

- 完整 YAML 文件内容。
- 一个最小执行命令示例。
- 一段“你需要改的参数”列表（只列必须改动项）。

可选附加输出（用户要求时）：

- JSON 版本配置。
- 多设备并发版本。
- 循环压测建议（通过 CLI `-l N` 或 `-i`，不在配置内重复实现外层循环）。
- 问题清单表（严重级别、位置、原因、修复建议）。

## 审查模式输出模板

当用户请求“帮我检查配置/看哪里错了”时，按以下格式输出：

1. Findings（按 blocker -> major -> minor）
2. Open Questions（仅列阻塞修复的问题）
3. Minimal Patch Plan（最小修改步骤）
4. 验证命令（单轮 + 循环）

## scripts 工具约定

本目录可附带轻量脚本用于离线校验与批量检查。

- 入口说明：`scripts/README.md`
- 配置体检脚本：`scripts/lint_autocom_config.py`

使用建议：

1. 先由智能体做语义审查（规则与场景理解）。
2. 再用脚本做机械校验（结构、引用、基础一致性）。
3. 两者结论冲突时，以人工审阅为准并记录到 `references/error-catalog.md`。

## 执行命令模板

```bash
# 基础执行
autocom -d dicts/xxx.yaml

# 循环 N 次
autocom -d dicts/xxx.yaml -l 3

# 无限循环
autocom -d dicts/xxx.yaml -i

# 叠加 config
autocom -d dicts/xxx.yaml -c configs/config.yaml
```

## 常见误区与纠偏

- 误区：把 `retry` 放在 `success_actions`。
  - 纠偏：`retry` 应放 `error_actions`。
- 误区：只给 Commands，不给 Devices。
  - 纠偏：默认输出完整配置，除非用户明确只要片段。
- 误区：把 CLI 循环逻辑写进配置结构。
  - 纠偏：循环由 CLI 参数 `-l/-i` 控制。
- 误区：随意假设模组支持某 AT 指令。
  - 纠偏：先确认模组型号或让用户提供已验证指令。
- 误区：把并行策略用于存在先后依赖的命令链。
  - 纠偏：依赖链使用 `sequential`，仅独立命令使用 `parallel`。
- 误区：扫描/联网类命令沿用默认超时导致误判失败。
  - 纠偏：按场景提升 timeout 并增加重试。

## 参考文件索引

| 文件                                   | 用途                                 |
| -------------------------------------- | ------------------------------------ |
| `references/format.md`                 | 配置结构与字段说明                   |
| `references/actions-catalog.md`        | Action 白名单与参数结构              |
| `references/command-reference.user.md` | 用户自定义 AT 指令参考               |
| `references/device-profiles.user.md`   | 用户设备参数画像（端口/波特率/特性） |
| `examples/common-patterns.md`          | 常见场景组合                         |
| `examples/user-custom-patterns.md`     | 用户自定义场景样例                   |
| `templates/wifi-module.yaml`           | WiFi 场景模板                        |
| `templates/ble-module.yaml`            | BLE 场景模板                         |
| `references/error-catalog.md`          | 常见错误与修复映射                   |
| `scripts/README.md`                    | 脚本使用说明                         |
| `scripts/lint_autocom_config.py`       | 离线配置体检脚本                     |

## 典型请求与响应策略

| 用户说                       | 正确响应                                                              |
| ---------------------------- | --------------------------------------------------------------------- |
| 帮我写一个 WiFi 连接测试配置 | 用 `templates/wifi-module.yaml` 生成完整配置，标注 SSID/密码/端口待填 |
| BLE 扫描怎么写               | 提供最小可运行 BLE 扫描完整 YAML（含 Devices + Commands）             |
| retry 放在哪里               | 明确在 `error_actions`，并给可复制片段                                |
| 多设备并行怎么做             | 给 `concurrent_strategy: parallel` 示例并提醒设备命名一致性           |
| 帮我做循环压测               | 输出配置 + 推荐 CLI：`-l N` 或 `-i`，不在配置中重复外层循环           |

## 不应做的事

- 不输出与项目结构不一致的字段名。
- 不发明未在 `references/actions-catalog.md` 中定义的 action。
- 不在缺少关键参数时直接给“看似可跑”的配置。
- 不在用户请求审查时只给“重写版”而不指出原配置错误点。
