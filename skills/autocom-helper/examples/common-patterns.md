# 常见流水线模式

## 1. 基础通信测试

```yaml
Devices:
  - name: DUT
    port: COM66
    baud_rate: 115200

Steps:
  - id: basic_at
    name: "验证 AT 通信"
    type: serial
    device: DUT
    send: "AT"
    expect: ["OK"]
    timeout: 3
    on_error: retry(3)
```

---

## 2. WiFi 连接测试

```yaml
Constants:
  SSID: "TestWiFi"
  PASSWORD: "Pass123456"

Steps:
  - id: set_mode
    name: "设置为 Station 模式"
    type: serial
    device: DUT
    send: "AT+CWMODE=1"
    expect: ["OK"]
    timeout: 5

  - id: wait_ready
    name: "等待模组就绪"
    type: wait
    duration: 2000

  - id: connect_wifi
    name: "连接 WiFi"
    type: serial
    device: DUT
    send: 'AT+CWJAP="{SSID}","{PASSWORD}"'
    expect: ["OK", "WIFI GOT IP"]
    timeout: 30
    on_error: retry(3)
    capture:
      ip: 'GOT IP:? ?(\d+\.\d+\.\d+\.\d+)'

  - id: get_ip
    name: "获取 IP 地址"
    type: serial
    device: DUT
    send: "AT+CIFSR"
    expect: ["OK"]
    timeout: 5
    capture:
      sta_ip: 'STAIP,"(.+?)"'

  - id: print_result
    name: "打印连接结果"
    type: action_batch
    actions:
      - print: "IP: {{ steps.get_ip.capture.sta_ip }}"
```

---

## 3. WiFi 扫描

```yaml
Steps:
  - id: set_mode
    type: serial
    device: DUT
    send: "AT+CWMODE=1"
    expect: ["OK"]
    timeout: 5

  - id: scan
    type: serial
    device: DUT
    send: "AT+CWLAP"
    expect: ["OK"]
    timeout: 15
    capture:
      aps: 'CWLAP:"(.+?)"'
    on_error: skip

  - id: print_scan
    type: action_batch
    actions:
      - print: "APs: {{ steps.scan.capture.aps }}"
```

---

## 4. BLE 广播与扫描

```yaml
Constants:
  BLE_NAME: "AutoCom_BLE"

Steps:
  - id: set_adv_name
    name: "设置 BLE 名称"
    type: serial
    device: DUT
    send: 'AT+BLENAME="{BLE_NAME}"'
    expect: ["OK"]
    timeout: 5

  - id: start_adv
    name: "启动广播"
    type: serial
    device: DUT
    send: "AT+BLEADV=1"
    expect: ["OK"]
    timeout: 5

  - id: wait_connection
    name: "等待传入连接"
    type: serial_wait
    device: DUT
    expect: ["CONNECTED", "_CONNECTED"]
    timeout: 60
```

---

## 5. BLE 连接

```yaml
Constants:
  TARGET_MAC: "AA:BB:CC:DD:EE:FF"

Steps:
  - id: set_mode
    type: serial
    device: DUT
    send: "AT+BLEMODE=1"
    expect: ["OK"]
    timeout: 5

  - id: scan_target
    type: serial
    device: DUT
    send: 'AT+BLESCAN=10'
    expect: ["OK"]
    timeout: 15

  - id: connect
    type: serial
    device: DUT
    send: 'AT+BLECONN=0,"{TARGET_MAC}"'
    expect: ["OK", "_CONNECTED"]
    timeout: 15
    on_error: retry(2)
```

---

## 6. HTTP 与 Ping

### 6.1 HTTP GET

```yaml
Steps:
  - id: http_get
    type: http
    url: "http://httpbin.org/get"
    method: GET
    expect:
      status_code: 200
    timeout: 15
    capture:
      origin: '"origin": "(.+?)"'
```

### 6.2 Ping 测试

```yaml
Steps:
  - id: ping
    type: serial
    device: DUT
    send: 'AT+PING="114.114.114.114"'
    expect: ["OK", "+PING:"]
    timeout: 15
    on_error: skip
```

### 6.3 TCP 连接

```yaml
Constants:
  SERVER_IP: "192.168.1.100"
  SERVER_PORT: 8080

Steps:
  - id: tcp_connect
    type: serial
    device: DUT
    send: 'AT+SAVETRANSLINK=1,"{SERVER_IP}","{SERVER_PORT}","TCP"'
    expect: ["OK", "CONNECT"]
    timeout: 15
```

---

## 7. MQTT 测试

```yaml
Constants:
  BROKER: "mqtt://broker.emqx.io:1883"
  CLIENT_ID: "TestClient_001"
  TOPIC: "test/autocom"

Steps:
  - id: mqtt_config
    type: serial
    device: DUT
    send: 'AT+MQTTCONFIG="{BROKER}","{CLIENT_ID}","","",0,0'
    expect: ["OK"]
    timeout: 5

  - id: mqtt_connect
    type: serial
    device: DUT
    send: "AT+MQTTCONN=0"
    expect: ["OK", "+MQTTCONN"]
    timeout: 15

  - id: mqtt_sub
    type: serial
    device: DUT
    send: 'AT+MQTTSUB="{TOPIC}",1'
    expect: ["OK"]
    timeout: 5

  - id: mqtt_pub
    type: serial
    device: DUT
    send: 'AT+MQTTPUB="{TOPIC}","Hello from AutoCom",1,0'
    expect: ["OK"]
    timeout: 5

  - id: mqtt_disconn
    type: serial
    device: DUT
    send: "AT+MQTTDISCONN"
    expect: ["OK"]
    timeout: 5
```

---

## 8. OTA 升级

```yaml
Constants:
  OTA_URL: "http://192.168.1.100:8080/firmware.bin"

Steps:
  - id: get_version
    type: serial
    device: DUT
    send: "AT+GMR"
    expect: ["OK"]
    timeout: 5
    capture:
      version: 'SDK version:(.+?)\r'

  - id: do_ota
    type: serial
    device: DUT
    send: 'AT+OTACONFIG="{OTA_URL}",1'
    expect: ["OK", "+OTARESULT"]
    timeout: 120
    on_error: retry(2)

  - id: post_ota_wait
    type: wait
    duration: 5000

  - id: verify_version
    type: serial
    device: DUT
    send: "AT+GMR"
    expect: ["OK"]
    timeout: 5
    capture:
      new_version: 'SDK version:(.+?)\r'

  - id: print_versions
    type: action_batch
    actions:
      - print: "旧版本: {{ steps.get_version.capture.version }}"
      - print: "新版本: {{ steps.verify_version.capture.new_version }}"
```

---

## 9. 多设备流水线

```yaml
Devices:
  - name: WiFi_Dev
    port: COM66
    baud_rate: 115200
  - name: BLE_Dev
    port: COM67
    baud_rate: 115200

Steps:
  - id: wifi_check
    type: serial
    device: WiFi_Dev
    send: "AT"
    expect: ["OK"]
    timeout: 3

  - id: ble_check
    type: serial
    device: BLE_Dev
    send: "AT"
    expect: ["OK"]
    timeout: 3

  - id: wifi_connect
    type: serial
    device: WiFi_Dev
    send: 'AT+CWJAP="{SSID}","{PASSWORD}"'
    expect: ["OK", "WIFI GOT IP"]
    timeout: 30

  - id: ble_adv
    type: serial
    device: BLE_Dev
    send: "AT+BLEADV=1"
    expect: ["OK"]
    timeout: 5
```

---

## 10. 变量捕获与复用

```yaml
Steps:
  - id: get_csq
    type: serial
    device: DUT
    send: "AT+CSQ"
    expect: ["OK"]
    timeout: 5
    capture:
      rssi: '\+CSQ: (\d+)'

  - id: check_signal
    type: action_batch
    actions:
      - print: "信号强度: {{ steps.get_csq.capture.rssi }}"
      - save:
          to: constants.rssi_value
          value: "{{ steps.get_csq.capture.rssi }}"
```

---

## 11. 循环/稳定性测试

```yaml
Config:
  description: "WiFi 重连 100 次"
  mode: loop
  loop:
    iterations: 100
    interval_ms: 2000
    stop_on_failure: true

Devices:
  - name: DUT
    port: COM66
    baud_rate: 115200

Constants:
  SSID: "TestWiFi"
  PASSWORD: "Pass123456"

Steps:
  - id: connect
    type: serial
    device: DUT
    send: 'AT+CWJAP="{SSID}","{PASSWORD}"'
    expect: ["OK", "WIFI GOT IP"]
    timeout: 30
    on_error: retry(2)

  - id: disconnect
    type: serial
    device: DUT
    send: "AT+CWQAP"
    expect: ["OK"]
    timeout: 5
```