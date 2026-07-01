# 流水线执行示例

## 场景

在设备上运行 SoftAP WiFi 配置流水线，然后循环 10 次以验证稳定性。

## 分步操作

### 1. 加载并检查流水线

```
load_pipeline(file_path="dicts/softap_steps.yaml")
```

返回包含设备、步骤、常量的配置摘要。确认：
- 设备端口和波特率正确
- 步骤列表非空
- 常量中包含正确的 SSID/密码

### 2. 运行前校验

```
validate_pipeline(file_path="dicts/softap_steps.yaml")
```

检查错误和告警。在继续运行前修复所有阻塞性问题。

### 3. 执行单轮

```
run_pipeline(file_path="dicts/softap_steps.yaml")
```

执行流水线一次。结果会显示每个步骤的执行情况。

### 4. 循环执行以验证稳定性

```
run_pipeline(file_path="dicts/softap_steps.yaml", loop_count=10, stop_on_failure=true)
```

执行 10 轮。如果任意一轮失败，流水线提前停止。

### 5. 限时压力测试

```
run_pipeline(file_path="dicts/softap_steps.yaml", duration="30s", stop_on_failure=false)
```

在 30 秒内尽可能多地执行轮次，记录所有失败但不停止。

### 6. 使用配置覆盖

```
run_pipeline(
  file_path="dicts/softap_steps.yaml",
  loop_count=5,
  config_overrides={
    "Devices": [{"name": "DeviceA", "port": "COM16", "baud_rate": 115200}],
    "Constants": {"SSID": "TestWiFi", "PASSWORD": "test123"}
  }
)
```

覆盖配置文件中的设备和常量，而不修改原文件。

## 输出文件

执行后，检查以下文件：

```
device_logs/{timestamp}/EXECUTION.log    — 步骤级执行跟踪
device_logs/{timestamp}/DeviceA.log      — DeviceA 的原始串口 I/O
device_logs/{timestamp}/EXECUTION.json   — 结构化结果
```

## 流水线配置示例

```yaml
Devices:
  - name: DeviceA
    port: COM16
    baud_rate: 115200

Constants:
  Target_SSID: "HomeWiFi"
  Target_PASSWORD: "securepass"

Steps:
  - id: check_comms
    type: serial
    device: DeviceA
    send: "AT"
    expect: ["OK"]
    timeout: 3

  - id: set_ap_mode
    type: serial
    device: DeviceA
    send: "AT+CWMODE=2"
    expect: ["OK"]
    timeout: 5

  - id: push_config
    name: "通过 SoftAP 推送 WiFi"
    type: action_batch
    actions:
      - post_wifi_config_once:
          device_ip: "192.168.1.1"
          ssid: "{Target_SSID}"
          password: "{Target_PASSWORD}"
          timeout: 5
          repeat: 3
          repeat_interval: 0.5

  - id: verify_connect
    type: serial
    device: DeviceA
    send: "AT+CWJAP?"
    expect: ["+CWJAP:", "OK"]
    timeout: 10
```