# Action 参考目录（可分发版）

本文件是 autocom-helper 的内置 Action 白名单与参数参考。仅当 action 在此文件中定义时，智能体才应推荐使用。

## 说明

- 该目录用于独立分发，不依赖仓库外文档。
- 如你的项目新增了 action，请在本文件追加。
- 新增 action 时，请提供：名称、用途、最小参数、示例。

## 基础动作

### print

- 用途: 输出提示消息
- 格式:

```json
{"print": "message"}
```

### wait

- 用途: 等待指定毫秒
- 格式:

```json
{"wait": {"duration": 1000}}
```

### retry

- 用途: 失败后重试
- 格式:

```json
{"retry": 3}
```

### save

- 用途: 保存变量
- 格式:

```json
{"save": {"device": "DUT", "variable": "var_name", "value": "value"}}
```

### save_conditional

- 用途: 正则提取并保存变量
- 格式:

```json
{"save_conditional": {"device": "DUT", "variable": "ip", "pattern": "regex"}}
```

## 设备/流程控制动作

### set_status

```json
{"set_status": "enabled"}
```

### set_status_by_order

```json
{"set_status_by_order": {"order": 2, "status": "disabled"}}
```

### execute_command

```json
{"execute_command": {"command": "AT", "timeout": 1000}}
```

### execute_command_by_order

```json
{"execute_command_by_order": 3}
```

## 数据处理动作

### generate_random_str

```json
{"generate_random_str": {"device": "DUT", "variable": "token", "length": 16}}
```

### calculate_length

```json
{"calculate_length": {"device": "DUT", "variable": "len", "data": "abc"}}
```

### calculate_crc

```json
{"calculate_crc": {"device": "DUT", "variable": "crc", "raw_data": "ABC"}}
```

### replace_str

```json
{"replace_str": {"device": "DUT", "variable": "out", "data": "abc", "original_str": "a", "new_str": "A"}}
```

## 网络相关动作

### wifi_connect

```json
{"wifi_connect": {"ssid": "MyWiFi", "password": "Pass", "timeout": 10}}
```

### get_wifi_config

```json
{"get_wifi_config": {"device_ip": "192.168.1.1", "ssid": "MyWiFi", "password": "Pass"}}
```

### post_wifi_config

```json
{"post_wifi_config": {"device_ip": "192.168.1.1", "ssid": "MyWiFi", "password": "Pass"}}
```

### get_network_page

```json
{"get_network_page": {"device_ip": "192.168.1.1", "url": "/"}}
```

### send_file

```json
{"send_file": "certs/server.crt"}
```

扩展格式:

```json
{"send_file": {"path": "config.txt", "line_ending": "crlf", "encoding": "utf-8"}}
```

## 用户自定义动作（预留）

在这里追加你的自定义 action，并给出 JSON 示例。建议格式：

```markdown
### my_custom_action
- 用途: ...
- 格式:
```json
{"my_custom_action": {...}}
```

```
