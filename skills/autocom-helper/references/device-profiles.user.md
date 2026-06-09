# 用户设备画像（预留）

本文件用于沉淀你的设备差异，帮助 autocom-helper 生成更稳健的配置。

## 建议字段

| 设备名 | 串口 | 波特率 | data_bits | parity | stop_bits | 备注 |
|--------|------|--------|-----------|--------|-----------|------|
| DUT_WiFi | COM66 | 115200 | 8 | null | 1 | |
| DUT_BLE | COM67 | 115200 | 8 | null | 1 | |

## 特殊行为记录（可选）

- 某设备首次上电需 wait 3000ms
- 某设备 AT+HTTPCLIENT 建议 timeout >= 15000
- 某设备在并行模式下不稳定，需 sequential
