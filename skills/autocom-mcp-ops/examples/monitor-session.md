# 持久会话监视示例

## 场景

在交互式发送指令的同时，持续监视设备的串口输出。设备会主动上报状态消息，我们需要捕获所有数据。

## 分步操作

### 1. 打开带后台监视的会话

```
serial_session_open(port="COM16", baud_rate=115200, monitor=True)
```

返回：
```
session_id = "sess_a1b2c3d4"
```

会话现已打开。一个后台线程持续将所有接收到的数据累积到 5000 行缓冲区中。

### 2. 发送指令并读取响应

```
serial_session_send(session_id="sess_a1b2c3d4", command="AT")
```

返回：
```
response = "AT\r\nOK\r\n"
matched = "OK"
elapsed_ms = 12
```

```
serial_session_send(session_id="sess_a1b2c3d4", command="AT+CSQ")
```

返回：
```
response = "+CSQ: 22,99\r\n\r\nOK\r\n"
matched = "OK"
```

### 3. 读取后台监视缓冲区

在发送指令期间，设备可能发送了主动上报消息：

```
serial_session_read(session_id="sess_a1b2c3d4")
```

返回：
```
data = "URC: WIFI_DISCONNECTED\r\nURC: WIFI_RECONNECTED\r\n"
bytes_count = 57
```

### 4. 列出活跃会话

```
serial_session_list
```

返回：
```
sessions = [
  {
    session_id: "sess_a1b2c3d4",
    port: "COM16",
    monitor: true,
    monitor_bytes: 1024,
    monitor_duration_seconds: 30.5
  }
]
```

### 5. 关闭会话

```
serial_session_close(session_id="sess_a1b2c3d4")
```

返回：成功

## 使用场景

- **模块启动序列**：以 monitor=True 打开会话，给模块重新上电，读取完整的启动日志
- **AT 指令调试**：打开会话，交互式发送指令，检查原始响应
- **长期监视**：打开后台监视，定期检查，完成后关闭
- **URC 监听**：设备发送主动上报状态码——后台监视会捕获所有消息

## 常见问题

- **未关闭的会话**：会话会占用串口——完成后务必关闭
- **缓冲区溢出**：最大 5000 行；如读取不够频繁，旧数据会被丢弃
- **过期会话**：如果设备断开后重新连接，会话的串口句柄将失效——需要关闭并重新打开