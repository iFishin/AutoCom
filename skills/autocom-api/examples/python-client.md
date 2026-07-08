# 调用示例

## 前提

```bash
pip install httpx  # 或 requests
# 启动服务
autocom api --port 8000
```

## 基础调用

```python
import httpx

BASE = "http://localhost:8000"
api = httpx.Client(base_url=BASE)

# 健康检查
print(api.get("/api/health").json())

# 列出串口
ports = api.get("/api/ports").json()
for d in ports["devices"]:
    print(f"  {d['device']}: {d['description']}")
```

## 单次指令

```python
port = "COM16"

# 发 AT
r = api.post(f"/api/ports/{port}/command", params={"command": "AT"})
print(r.json()["response"])  # "AT\r\nOK\r\n"

# 带参数
r = api.post(f"/api/ports/{port}/command", params={
    "command": "AT+CSQ", "baud_rate": 115200, "timeout": 10
})
```

## 扫描波特率

```python
r = api.post(f"/api/ports/{port}/baud-scan", json={
    "test_command": "AT", "expected_response": "OK"
})
data = r.json()
print(f"可用波特率: {data['working_rates']}")
```

## 持久会话

```python
# 打开
s = api.post("/api/sessions", params={"port": port, "baud_rate": 115200}).json()
sid = s["session_id"]

# 交互
api.post(f"/api/sessions/{sid}/send", params={"command": "AT"})
api.post(f"/api/sessions/{sid}/send", params={"command": "AT+CGMR"})
rx = api.post(f"/api/sessions/{sid}/read")
print(rx.json()["data"])

# 关闭
api.delete(f"/api/sessions/{sid}")
```

## 诊断

```python
# 信号线
pin = api.get(f"/api/ports/{port}/pin-status").json()
print(f"DSR={pin['dsr']} CTS={pin['cts']}")

# 延迟
lat = api.post(f"/api/ports/{port}/latency", params={"rounds": 5}).json()
print(f"RTT: {lat['rtt_ms']['avg']}ms")

# hex 查看
hex = api.get(f"/api/ports/{port}/hex-dump", params={"bytes_to_read": 64}).json()
for line in hex["hex_dump"]:
    print(f"{line['offset']:08x}  {line['hex']}  |{line['ascii']}|")
```

## 流水线

```python
# 校验
r = api.post("/api/pipeline/validate", params={"file_path": "dicts/test.yaml"})
print(r.json())

# 干运行
r = api.post("/api/pipeline/dry-run", params={"file_path": "dicts/test.yaml"})

# 单步调试
r = api.post("/api/pipeline/step-debug", params={
    "file_path": "dicts/test.yaml", "step_id": "connect_wifi"
})

# 执行
r = api.post("/api/pipeline/run", params={
    "file_path": "dicts/test.yaml", "loop_count": 10, "stop_on_failure": True
})
```

## 执行历史

```python
# 列表
r = api.get("/api/executions", params={"limit": 5}).json()
for s in r["sessions"]:
    print(f"{s['session_id']}  logs={s['device_logs']}")

# 详情
sid = r["sessions"][0]["session_id"]
detail = api.get(f"/api/executions/{sid}").json()

# 搜索
r = api.get(f"/api/executions/{sid}/search", params={"keyword": "FAIL"})
for m in r["matches"]:
    print(f"  {m['file']}:{m['line']} {m['text']}")
```

## 设备配置

```python
# 保存
api.post("/api/profiles", params={
    "name": "my_device", "port": "COM16", "baud_rate": 115200
})

# 列出
profiles = api.get("/api/profiles").json()
for p in profiles["profiles"]:
    print(f"{p['name']} -> {p['port']} @ {p['baud_rate']}")

# 删除
api.delete("/api/profiles/my_device")
```