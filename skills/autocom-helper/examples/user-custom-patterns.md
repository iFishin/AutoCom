# 用户自定义流水线模式

把你常用的业务场景放到这里，autocom-helper 会优先参考此文件来生成配置。

## 模板

### 场景: <名称>

```yaml
Config:
  description: "<说明>"
  mode: single      # 或 "loop"

Devices:
  - name: <设备名>
    port: <COMx>
    baud_rate: 115200

Constants:
  KEY: "value"

Steps:
  - id: step_1
    type: serial
    device: <设备名>
    send: "<指令>"
    expect: ["OK"]
    timeout: 5
```

### 场景: WiFi 重连稳定性

- 目标: 连续重连 100 次，统计失败率
- 设备: DUT
- 关键指令: AT+CWMODE=1, AT+CWJAP, AT+CWQAP
- 推荐超时: 连接 30s, 断开 5s

### 场景: BLE 扫描回归

- 目标: 扫描结果中必须包含目标名称
- 设备: DUT
- 关键指令: AT+BLENAME, AT+BLEADV=1, AT+BLESCAN
- 推荐超时: 扫描 15s