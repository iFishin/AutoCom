# About AutoCom

[TOC]

## 背景

在前期日常测试以及压力挂测中，发现了内部自动化测试以及压力测试存在诸多不便之处。在内部压力脚本中，由于每一个人的代码逻辑不一，规范标准不同，导致一套脚本不能通用，更别说做更多的扩展和维护。

新产业需要标准，新技术需要标准，同样，自动化测试也需要标准。AutoCom的诞生就是为了满足这一需求。

那么，AutoCom能解决哪些问题呢？

1. **统一标准**：通过提供一套指令执行字典，只要编写遵循规范，就能实现自动化测试用例的快速编写和复用。
2. **提高效率**：借助AutoCom以及指令执行字典，用户可以快速查找和使用已有的测试用例和脚本，减少重复劳动。
3. **便于维护**：统一的指令执行字典规范，使得这一套执行字典能更好的迁移至其他项目中，降低了维护成本。
4. **支持扩展**：AutoCom提供了ActionHandler，能根据捕获的的响应结果智能调用用户自定义方法。

## 怎么个规范？

依托于指令执行字典，AutoCom制定了一套指令执行字典编写规范，只有规范化的指令步骤编写，才能保证测试用例的正常执行。

指令执行字典，本质为一个 JSON 对象，包含了一系列的指令和设备参数。

结构为：
```json
{
    "ConfigForDevices": {
        ...
    },
    "Devices": [
        ...
    ],
    "ConfigForActions": {
        ...
    },
    "ConfigForCommands": {
        ...
    },
    "Commands": [
        ...
    ]
}
```

其中主要的部分是 `Devices` 和 `Commands`。`Devices` 定义了测试中使用的设备及其配置，而 `Commands` 则定义了可执行的指令及其参数。通过这种方式，AutoCom 能够实现设备的统一管理，从而在指令执行时能够选择性的调用设备执行。

`Devices` 的结构如下：

```json
{
    "name": "DeviceA",
    "status": "enabled",
    "port": "COM66",
    "baud_rate": 115200,
    "stop_bits": 1,
    "parity": null,
    "data_bits": 8,
    "flow_control": {
        "xon_xoff": false,
        "rts_cts": false,
        "dsr_dtr": false
    },
    "dtr": false,
    "rts": false
}
```

`Commands` 的结构如下：

```json
 {
    "command": "AT+QRST",
    "status": "enabled",
    "expected_responses": [
        "OK",
        "RDY"
    ],
    "device": "DeviceA",
    "order": 1,
    "parameters": [],
    "timeout": 2000,
    "concurrent_strategy": "sequential",
    "success_actions": [
        {
            "set_status": "disabled"
        }
    ],
    "success_response_actions": [
    ],
    "error_actions": [
        {
            "retry": 3
        }
    ],
    "error_response_actions": [
    ]
}
```

## 效果是怎样？

| File Name                     | Description                                                  |
| ----------------------------- | ------------------------------------------------------------ |
| DebugA_dev_ttyUSB1_115200.log | Devices列表中的`DebugA`设备，该设备串口号为`ttyUSB1`，波特率为`115200` |
| DeviceA_dev_ttyUSB0_9600.log  | Devices列表中的`DeviceA`设备，该设备串口号为`ttyUSB0`，波特率为`9600` |
| EXECUTION_LOG.log             | 执行总概                                                     |
| reboot_sta_reconnect.json     | 指令执行字典                                                 |

## 如何智能化？

灵感来自 GitHub 的 Github Actions，AutoCom 也引入了类似的概念。

使用 AutoCom 的 ActionHandler，用户可以根据捕获的响应结果智能调用自定义方法。ActionHandler 允许用户在指令执行过程中定义一系列动作，这些动作可以在指令执行成功或失败时触发。

当然也可以在全局中设置 ActionHandler，以便在执行过程中对捕获到异常结果做出特定响应。

## 更多交互功能拓展

AutoCom 提供了一个 指令执行字典 标准，后续可以据此来实现更多流水线交互功能。下面介绍目前我在弄的几个拓展功能：

- SCOM 与 AutoCom 的集成：通过 SCOM 调试后的指令执行字典，可以直接导出为 AutoCom 的指令执行字典格式，便于在 AutoCom 中使用。

- 大模型 与 AutoCom 的集成：通过大模型的智能分析和生成能力，可以自动化生成指令执行字典，通过维护知识库以及相应的手册，使用者可以用对话的方式来生成或者执行测试用例。

## 未来可能规划

- AutoCom 打算会集成在某个 自动化测试平台 中，作为一个插件使用。参考市面的pytest、 vtest、 unittest 等测试框架。或者类似Github Action集成在 CI/CD 流水线中。
- 后续会考虑部署一个 AutoCom 服务平台，供研发和测试提供海量测试用例执行字典，供使用者一键拉取本地执行，快速执行并发现问题。
- 后续会持续跟进 大模型 Function Calling 的发展，集成大模型的智能分析和生成能力，自动化生成指令执行字典。

| IDX  | Future                                                       |
| ---- | ------------------------------------------------------------ |
| 1    | AutoCom 打算会集成在某个 自动化测试平台 中，作为一个插件使用。参考市面的pytest、 vtest、 unittest 等测试框架。或者类似Github Action集成在 CI/CD 流水线中。 |
| 2    | 后续会考虑部署一个 AutoCom 服务平台，供研发和测试提供海量测试用例执行字典，供使用者一键拉取本地执行，快速执行并发现问题。 |
| 3    | 后续会持续跟进 大模型 Function Calling 的发展，集成大模型的智能分析和生成能力，自动化生成指令执行字典。 |