# Actions 操作项

本文档自动生成自 `utils/ActionHandler.py`，记录所有可用的 action 操作项。

> 💡 **提示**: 此文档可通过脚本自动更新。运行 `python scripts/update_actions_doc.py` 来同步最新的 action 操作项定义。

## 快速参考表

| Action | 格式 | 说明 |
| :--- | :--- | :--- |
| test | `{"test": "message"}` | 测试功能 |
| save | `{"save": {"device": "...", "variable": "...", "value": "..."}}` | 保存数据 |
| save_conditional | `{"save_conditional": {"device": "...", "variable": "...", "pattern": "..."}}` | 条件保存数据 |
| retry | `{"retry": 3}` | 重试指令 |
| set_status | `{"set_status": "enabled"}` | 设置指令状态 |
| wait | `{"wait": {"duration": 1000}}` | 等待 |
| print | `{"print": "message"}` | 打印消息 |
| set_status_by_order | `{"set_status_by_order": {"order": 2, "status": "..."}}` | 通过序号设置状态 |
| execute_command | `{"execute_command": {"command": "...", "timeout": 1000}}` | 执行命令 |
| execute_command_by_order | `{"execute_command_by_order": 3}` | 通过序号执行命令 |
| generate_random_str | `{"generate_random_str": {"device": "...", "variable": "...", "length": 100}}` | 生成随机字符串 |
| calculate_length | `{"calculate_length": {"device": "...", "variable": "...", "data": "..."}}` | 计算字符串长度 |
| calculate_crc | `{"calculate_crc": {"device": "...", "variable": "...", "raw_data": "..."}}` | 计算 CRC 校验值 |
| replace_str | `{"replace_str": {"device": "...", "variable": "...", "data": "...", "original_str": "...", "new_str": "..."}}` | 字符串替换 |
| wifi_connect | `{"wifi_connect": {"ssid": "...", "password": "...", "timeout": 10}}` | 连接 WiFi |
| get_wifi_config | `{"get_wifi_config": {"device_ip": "...", "ssid": "...", "password": "..."}}` | 发送 WiFi 配置 |
| post_wifi_config | `{...}` | 发送WiFi配置到指定设备IP (通过GET请求) |
| get_network_page | `{"get_network_page": {"device_ip": "...", "url": "/"}}` | 获取网络页面 |
| send_file | `{"send_file": "path/to/file.txt"}` | 发送文件到设备 |

## 详细说明

### test

**说明:** 测试功能

**格式:**
```json
{
    "test": "test_message"
}
```

---

### save

**说明:** 保存数据功能

**格式:**
```json
{
    "save": {
        "device": "device_name",
        "variable": "variable_name",
        "value": "value_to_save"
    }
}
```

---

### save_conditional

**说明:** 条件保存数据功能

**格式:**
```json
{
    "save_conditional": {
        "device": "device_name",
        "variable": "variable_name",
        "pattern": "regex_pattern"
    }
}
```

---

### retry

**说明:** 重试命令功能

**格式:**
```json
{
    "retry": retry_times
}
```

---

### set_status

**说明:** 设置状态功能

**格式:**
```json
{
    "set_status": "status_value"
}
```

---

### wait

**说明:** 等待功能

**格式:**
```json
{
    "wait": {
        "duration": wait_time_in_milliseconds
    }
}
```

---

### print

**说明:** 打印消息功能

**格式:**
```json
{
    "print": "message_to_print"
}
```

---

### set_status_by_order

**说明:** 通过序号设置状态功能

**格式:**
```json
{
    "set_status_by_order": {
        "order": command_order,
        "status": "status_value"
    }
}
```

---

### execute_command

**说明:** 执行命令功能

**格式:**
```json
{
    "execute_command": {
        "command": "command_string",
        "timeout": timeout_in_milliseconds
    }
}
```

---

### execute_command_by_order

**说明:** 通过序号执行命令功能

**格式:**
```json
{
    "execute_command_by_order": command_order
}
```

---

### generate_random_str

**说明:** 生成随机字符串功能

**格式:**
```json
{
    "generate_random_str": {
        "device": "device_name",
        "variable": "variable_name",
        "length": string_length
    }
}
```

---

### calculate_length

**说明:** 计算字符串长度功能

**格式:**
```json
{
    "calculate_length": {
        "device": "device_name",
        "variable": "variable_name",
        "data": "string_to_calculate"
    }
}
```

---

### calculate_crc

**说明:** 计算 CRC 功能

**格式:**
```json
{
    "calculate_crc": {
        "device": "device_name",
        "variable": "variable_name",
        "raw_data": "data_to_calculate_crc"
    }
}
```

---

### replace_str

**说明:** 替换字符串功能

**格式:**
```json
{
    "replace_str": {
        "device": "device_name",
        "variable": "variable_name",
        "data": "original_string",
        "original_str": "string_to_replace",
        "new_str": "replacement_string"
    }
}
```

---

### wifi_connect

**说明:** 连接 WiFi 功能

**格式:**
```json
{
    "wifi_connect": {
        "ssid": "SSID",
        "password": "password",
        "timeout": 10  # 可选参数，连接超时时间(秒)
    }
}
```

---

### get_wifi_config

**说明:** 发送WiFi配置到指定设备IP (通过GET请求)

**格式:**
```json
{
    "get_wifi_config": {
        "device_ip": "192.168.88.1",
        "ssid": "MyWiFi",
        "password": "MyPassword"
    }
}
```

---

### post_wifi_config

**说明:** 发送WiFi配置到指定设备IP (通过GET请求)

**格式:**
```json
{
    "post_wifi_config": {
        "device_ip": "192.168.1.1",
        "ssid": "MyWiFi",
        "password": "MyPassword"
    }
}
```

---

### get_network_page

**说明:** 获取网络页面内容 (通过GET请求)

**格式:**
```json
{
    "get_network_page": {
        "device_ip": "192.168.19.1",
        "url": "/"
    }
}
```

---

### send_file

**说明:** 向设备串口发送文本文件功能（支持证书、配置文件等）

**格式:**
```json
{
    "send_file": "certs/server.crt"
}
```

**详细说明:**
- path: 文本文件路径，支持相对路径（基于当前工作目录 os.getcwd()）或绝对路径
        - encoding: 可选，文件编码方式，默认为 'utf-8'，可选 'gbk'、'latin-1' 等
        - line_ending: 可选，行结束符转换规则，默认为 'lf'
          * 'lf': 使用 LF（\\n，0x0a），Unix/Linux/Mac 风格
          * 'crlf': 使用 CRLF（\\r\\n，0x0d0a），Windows 风格
          * 'cr': 使用 CR（\\r，0x0d），旧 Mac 风格
          * 'none': 保持原样，不做转换

        行为:
        - 以文本模式读取文件，使用指定编码转换为字符串
        - 标准化行结束符（CRLF/LF/CR 都转为 LF）
        - 根据 line_ending

---

