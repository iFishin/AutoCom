# 硬件诊断示例

## 场景

COM16 上的设备对 AT 指令无响应。使用硬件诊断工具排查物理层问题。

## 分步操作

### 1. 确认端口存在

```
list_serial_ports
```

检查 COM16 是否出现在列表中，且描述和 VID/PID 符合预期。

### 2. 读取调制解调器信号线

```
serial_pin_status(port="COM16")
```

返回：
```
{
  cts: true,    // 允许发送——设备已就绪
  dsr: false,   // 数据设备就绪——LOW 可能表示设备已断电或未就绪
  dcd: false,   // 数据载波检测
  ri: false     // 振铃指示
}
```

如果 `dsr` 为 false，设备可能出现以下情况：
- 已断电
- 处于复位状态
- 连接不正确（TX/RX/GND 接线问题）

### 3. 执行回环测试

硬件回环（需要 TX 与 RX 短接）：

```
serial_loopback_test(port="COM16", mode="hardware", test_data="HelloAutoCom")
```

如果无法物理短接端口，可使用回声模式：

```
serial_loopback_test(port="COM16", mode="echo", probe_command="AT", probe_expected="OK")
```

### 4. 测量延迟

```
serial_latency_bench(port="COM16", rounds=10, test_data="AT")
```

返回 RTT 统计数据。115200 波特率下的典型值：
- 发送时间：< 5ms
- 首字节到达：1-10ms
- 完整 RTT：10-50ms

如果 RTT 持续大于 100ms，请检查：
- 双方是否实际配置为 115200 波特率
- USB 转串口适配器的缓冲设置
- 系统负载或驱动问题

### 5. 切换 DTR/RTS 进行硬件复位

某些模块在 DTR 从低变高时复位：

```
serial_pin_set(port="COM16", dtr=false)
// 等待 100ms
serial_pin_set(port="COM16", dtr=true)
```

复位后，监视启动消息：

```
monitor_serial_port(port="COM16", duration=5)
```

## 诊断流程图

```
设备无响应
│
├─ serial_pin_status -> DSR 为 false?
│   └─ 检查电源 / 接线
│
├─ serial_loopback_test -> 失败?
│   └─ 检查 TX/RX 接线 / 波特率
│
├─ serial_latency_bench -> RTT 偏高?
│   └─ 检查波特率 / 驱动缓冲区
│
└─ DTR/复位 + 监视 -> 无启动消息?
    └─ 设备可能已损坏或端口错误
```