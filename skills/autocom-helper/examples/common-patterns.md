# 常见 AT 指令组合示例

## 目录

1. [基础通信测试](#1-基础通信测试)
2. [WiFi 连接测试](#2-wifi-连接测试)
3. [WiFi Scan 扫描测试](#3-wifi-scan-扫描测试)
4. [BLE 广播与扫描](#4-ble-广播与扫描)
5. [BLE 连接测试](#5-ble-连接测试)
6. [网络通信测试](#6-网络通信测试)
7. [MQTT 测试](#7-mqtt-测试)
8. [OTA 升级测试](#8-ota-升级测试)
9. [多设备并发](#9-多设备并发)
10. [变量保存与引用](#10-变量保存与引用)

---

## 1. 基础通信测试

最简配置，仅验证串口通信是否正常。

```yaml
Devices:
  - name: DUT
    status: enabled
    port: COM66
    baud_rate: 115200

Commands:
  - command: "AT"
    device: DUT
    order: 1
    status: enabled
    expected_responses: ["OK"]
    timeout: 2000
    success_actions:
      - print: "✅ 通信正常"
    error_actions:
      - retry: 5
```

---

## 2. WiFi 连接测试

```yaml
Constants:
  SSID: "TestWiFi"
  PASSWORD: "Pass123456"

Commands:
  # 设置为 Station 模式
  - command: "AT+CWMODE=1"
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK"]
    timeout: 3000

  # 等待模组就绪
  - command: ""
    device: DUT_WiFi
    order: 2
    timeout: 100
    success_actions:
      - wait:
          duration: 2000

  # 连接 WiFi（使用变量）
  - command: 'AT+CWJAP="$SSID","$PASSWORD"'
    device: DUT_WiFi
    order: 3
    expected_responses: ["OK", "WIFI GOT IP"]
    timeout: 15000
    success_actions:
      - print: "✅ WiFi 连接成功"
    error_actions:
      - retry: 3

  # 获取 IP
  - command: "AT+CIFSR"
    device: DUT_WiFi
    order: 4
    expected_responses: ["OK"]
    timeout: 3000
    success_actions:
      - save_conditional:
          device: DUT_WiFi
          variable: local_ip
          pattern: '\\+CIFSR:STAIP,"(.+?)"'
      - print: "✅ WiFi 连接完成"
```

---

## 3. WiFi Scan 扫描测试

```yaml
Commands:
  - command: "AT+CWMODE=1"
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK"]
    timeout: 3000

  - command: "AT+CWLAP"
    device: DUT_WiFi
    order: 2
    expected_responses: ["OK"]
    timeout: 10000
    success_actions:
      - print: "✅ WiFi 扫描完成"
    error_actions:
      - print: "⚠️ 扫描失败或无热点"
```

---

## 4. BLE 广播与扫描

```yaml
Commands:
  # 设置广播模式
  - command: "AT+BLEMODE=0"
    device: DUT_BLE
    order: 1
    expected_responses: ["OK"]
    timeout: 3000

  # 设置广播名称
  - command: 'AT+BLENAME="Quectel_BLE"'
    device: DUT_BLE
    order: 2
    expected_responses: ["OK"]
    timeout: 3000

  # 开启广播
  - command: "AT+BLEADV=1"
    device: DUT_BLE
    order: 3
    expected_responses: ["OK"]
    timeout: 3000
    success_actions:
      - wait:
          duration: 3000
      - print: "✅ 广播已开启，等待主设备连接"
```

---

## 5. BLE 连接测试

```yaml
Constants:
  TARGET_MAC: "AA:BB:CC:DD:EE:FF"

Commands:
  # 设置为从机模式
  - command: "AT+BLEMODE=0"
    device: DUT_BLE
    order: 1
    expected_responses: ["OK"]
    timeout: 3000

  # 连接指定 MAC 地址
  - command: 'AT+BLECONN=0,"$TARGET_MAC"'
    device: DUT_BLE
    order: 2
    expected_responses: ["OK", "_CONNECTED"]
    timeout: 10000
    success_actions:
      - print: "✅ BLE 连接成功"
    error_actions:
      - print: "❌ BLE 连接失败"

  # 查询连接状态
  - command: "AT+BLECONN?"
    device: DUT_BLE
    order: 3
    expected_responses: ["OK"]
    timeout: 3000
    success_actions:
      - print: "✅ 连接状态查询成功"
```

---

## 6. 网络通信测试

### 6.1 HTTP GET

```yaml
Commands:
  - command: 'AT+HTTPCLIENT=1,0,"http://httpbin.org/get","","",""'
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK", "+HTTPCLIENT"]
    timeout: 15000
    success_actions:
      - print: "✅ HTTP GET 成功"
    error_actions:
      - print: "❌ HTTP 请求失败"
```

### 6.2 Ping 测试

```yaml
Commands:
  - command: 'AT+PING="www.baidu.com"'
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK", "+PING"]
    timeout: 10000
    success_actions:
      - print: "✅ 网络连通性正常"
    error_actions:
      - print: "❌ 网络 Ping 不通"
```

### 6.3 TCP 连接

```yaml
Constants:
  SERVER_IP: "192.168.1.100"
  SERVER_PORT: "8080"

Commands:
  # 建立 TCP 连接
  - command: 'AT+SAVETRANSLINK=1,"$SERVER_IP","$SERVER_PORT","TCP"'
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK", "CONNECT"]
    timeout: 10000
    success_actions:
      - print: "✅ TCP 连接已建立"
    error_actions:
      - print: "❌ TCP 连接失败"
```

---

## 7. MQTT 测试

```yaml
Constants:
  MQTT_BROKER: "mqtt://broker.emqx.io:1883"
  CLIENT_ID: "QuectelClient_001"
  TOPIC: "test/quectel"

Commands:
  # 配置 MQTT 参数
  - command: 'AT+MQTTCONFIG="$MQTT_BROKER","$CLIENT_ID","","",0,0'
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK"]
    timeout: 5000

  # 连接 Broker
  - command: "AT+MQTTCONN=0"
    device: DUT_WiFi
    order: 2
    expected_responses: ["OK", "+MQTTCONN"]
    timeout: 10000
    success_actions:
      - print: "✅ MQTT 连接成功"
    error_actions:
      - print: "❌ MQTT 连接失败"

  # 订阅主题
  - command: 'AT+MQTTSUB="$TOPIC",1'
    device: DUT_WiFi
    order: 3
    expected_responses: ["OK"]
    timeout: 5000
    success_actions:
      - print: "✅ 主题订阅成功"

  # 发布消息
  - command: 'AT+MQTTPUB="$TOPIC","Hello from AutoCom",1,0'
    device: DUT_WiFi
    order: 4
    expected_responses: ["OK"]
    timeout: 5000
    success_actions:
      - print: "✅ 消息发布成功"

  # 断开连接
  - command: "AT+MQTTDISCONN"
    device: DUT_WiFi
    order: 5
    expected_responses: ["OK"]
    timeout: 3000
    success_actions:
      - print: "✅ MQTT 已断开"
```

---

## 8. OTA 升级测试

```yaml
Constants:
  OTA_URL: "http://192.168.1.100:8080/firmware.bin"

Commands:
  # 查询当前固件版本
  - command: "AT+GMR"
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK"]
    timeout: 3000
    success_actions:
      - print: "✅ 当前固件版本已记录"
      - save_conditional:
          device: DUT_WiFi
          variable: old_version
          pattern: "SDK version:(.+?)\r"

  # 启动 OTA 升级
  - command: 'AT+OTACONFIG="$OTA_URL",1'
    device: DUT_WiFi
    order: 2
    expected_responses: ["OK", "+OTARESULT"]
    timeout: 120000     # OTA 时间较长，适当延长超时
    success_actions:
      - print: "✅ OTA 升级成功，正在重启..."
      - wait:
          duration: 5000
    error_actions:
      - print: "❌ OTA 升级失败"

  # 重启后验证版本
  - command: "AT+GMR"
    device: DUT_WiFi
    order: 3
    expected_responses: ["OK"]
    timeout: 5000
    success_actions:
      - print: "✅ 固件版本验证"
```

---

## 9. 多设备并发

同时测试 WiFi 模组和 BLE 模组：

```yaml
Devices:
  - name: DUT_WiFi
    status: enabled
    port: COM66
    baud_rate: 115200

  - name: DUT_BLE
    status: enabled
    port: COM67
    baud_rate: 115200

Commands:
  # 并行执行：同时测试两个设备的 AT 通信
  - command: "AT"
    device: DUT_WiFi
    order: 1
    status: enabled
    expected_responses: ["OK"]
    timeout: 2000
    concurrent_strategy: parallel
    success_actions:
      - print: "✅ WiFi AT 正常"

  - command: "AT"
    device: DUT_BLE
    order: 1
    status: enabled
    expected_responses: ["OK"]
    timeout: 2000
    concurrent_strategy: parallel
    success_actions:
      - print: "✅ BLE AT 正常"

  # 串行执行：WiFi 先连接，再 BLE 广播
  - command: "AT+CWMODE=1"
    device: DUT_WiFi
    order: 2
    expected_responses: ["OK"]
    timeout: 3000

  - command: "AT+BLEMODE=0"
    device: DUT_BLE
    order: 3
    expected_responses: ["OK"]
    timeout: 3000
```

---

## 10. 变量保存与引用

### 10.1 正则提取保存

```yaml
Commands:
  # 查询信号强度，提取数值保存
  - command: "AT+CSQ"
    device: DUT_WiFi
    order: 1
    expected_responses: ["OK"]
    timeout: 3000
    success_actions:
      - save_conditional:
          device: DUT_WiFi
          variable: rssi_value
          pattern: "\\+CSQ: (\\d+)"
      - print: "✅ 信号值已保存到变量"

  # 根据保存的变量值决定后续操作
  - command: 'AT+SEND_DATA="$rssi_value"'
    device: DUT_WiFi
    order: 2
    expected_responses: ["OK"]
    timeout: 3000
```

### 10.2 CRC 校验计算

```yaml
Commands:
  - command: ""
    device: DUT_WiFi
    order: 1
    timeout: 100
    success_actions:
      - calculate_crc:
          device: DUT_WiFi
          variable: crc_result
          raw_data: "Hello AutoCom"

  - command: 'AT+UPLOAD="$crc_result"'
    device: DUT_WiFi
    order: 2
    expected_responses: ["OK"]
    timeout: 5000
```

### 10.3 随机字符串生成

```yaml
Commands:
  - command: ""
    device: DUT_WiFi
    order: 1
    timeout: 100
    success_actions:
      - generate_random_str:
          device: DUT_WiFi
          variable: random_token
          length: 32

  - command: 'AT+REGISTER="$random_token"'
    device: DUT_WiFi
    order: 2
    expected_responses: ["OK"]
    timeout: 5000
    success_actions:
      - print: "✅ 随机 Token 注册成功"
```
