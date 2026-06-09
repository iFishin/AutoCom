# 日志诊断示例

## 输入日志片段

```text
[ERROR] Command AT+CWJAP=... timeout after 5000ms
[INFO] Retry 1/3
[ERROR] Command AT+CWJAP=... timeout after 5000ms
```

## 输出（示例）

### Findings

- [major] WiFi 连接命令 timeout 偏小（5000ms）
- [minor] 缺少连接前稳定等待（wait）

### Evidence

- 连续两次 AT+CWJAP 在 5000ms 超时

### Fix Plan

1. 将该命令 timeout 调整到 15000ms
2. 在连接命令前增加 wait 2000ms
3. error_actions 保留 retry: 3

### Validation

- 单轮: `autocom -d dicts/wifi_connect.yaml`
- 循环: `autocom -d dicts/wifi_connect.yaml -l 20`

```
