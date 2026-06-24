"""
AutoCom Context — 流水线运行时变量上下文

职责：
- 内存 dict 树 + dot-path 读写
- 每步结果自动同步到 SessionStore
- 兼容旧 DataStore API（store_data / get_data / get_constant）
- 类型保持（写 SQLite 时记录 value_type，读回来还原）

用法：
    ctx = Context(session_store, session_id)
    ctx.set("steps.check_fw.status", "passed")
    ctx.set("devices.DeviceA.rssi", 25)
    val = ctx.get("steps.check_fw.capture.version")  # → "1.2.3"
    ctx.record_step(step_id="check_fw", status="passed", ...)
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from components.SessionStore import SessionStore


class Context:
    """运行期上下文：内存树 + 自动持久化到 SessionStore。"""

    def __init__(self, store: SessionStore, session_id: str,
                 config_name: str = ""):
        self._store = store
        self._session_id = session_id
        self._data: dict = {}
        self._step_counter = 0

        # 自动创建 session（如果不存在）
        if not self._store.get_session(session_id):
            self._store.create_session(session_id, config_name=config_name)  # 自增的 step_index

    # ── 属性 ──

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def store(self) -> SessionStore:
        return self._store

    # ── Dot-path 读写 ──

    def get(self, path: str, default: Any = None) -> Any:
        """通过 dot-path 读取变量。

        ctx.get("steps.check_fw.capture.version")  # → "1.2.3"
        ctx.get("constants.SSID")                   # → "MyWiFi"
        """
        keys = path.split(".")
        d = self._data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, path: str, value: Any) -> None:
        """通过 dot-path 写入变量。中间路径会自动创建。"""
        keys = path.split(".")
        d = self._data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

    def has(self, path: str) -> bool:
        """检查 dot-path 是否存在。"""
        return self.get(path, _SENTINEL) is not _SENTINEL


    # ── 步骤记录 ──

    def record_step(self, step_id: str, *,
                    step_type: str = "",
                    status: str = "unknown",
                    send: str = "",
                    response: str = "",
                    elapsed_ms: int = 0,
                    error: str = "",
                    capture: dict = None) -> dict:
        """记录一步的执行结果到内存 + SQLite。"""
        entry = {
            "status": status,
            "step_type": step_type,
            "send": send,
            "response": response,
            "elapsed_ms": elapsed_ms,
            "error": error,
            "capture": capture or {},
        }
        # 写内存树
        self.set(f"steps.{step_id}", entry)
        # 写 SQLite
        idx = self._step_counter
        self._step_counter += 1
        self._store.save_step(
            self._session_id,
            step_id=step_id,
            step_index=idx,
            step_type=step_type,
            status=status,
            send=send,
            response=response,
            elapsed_ms=elapsed_ms,
            error=error,
            capture=capture,
        )
        return entry

    def get_step_result(self, step_id: str) -> Optional[dict]:
        """读取某一步的结果（优先内存，fallback SQLite）。"""
        val = self.get(f"steps.{step_id}")
        if val is not None:
            return val
        # fallback: 从 SQLite 读
        row = self._store.get_step(self._session_id, step_id)
        if row:
            # 解析 captured
            entry = {
                "status": row["status"],
                "step_type": row["step_type"],
                "send": row["send"],
                "response": row["response"],
                "elapsed_ms": row["elapsed_ms"],
                "error": row["error"],
                "capture": json.loads(row["captured"]) if row.get("captured") else {},
            }
            # 写回内存缓存
            self.set(f"steps.{step_id}", entry)
            return entry
        return None

    # ── Session 生命周期 ──

    def close_session(self, status: str = "completed",
                      summary: dict = None) -> None:
        """结束当前 session，写入摘要。"""
        if summary is None:
            counts = self._store.count_step_status(self._session_id)
            summary = {
                "total": sum(counts.values()),
                "passed": counts.get("passed", 0),
                "failed": counts.get("failed", 0),
                "skipped": counts.get("skipped", 0),
            }
        self._store.close_session(self._session_id, status, summary)

    def get_summary(self) -> dict:
        """获取当前 session 的执行摘要。"""
        counts = self._store.count_step_status(self._session_id)
        return {
            "session_id": self._session_id,
            "total": sum(counts.values()),
            "passed": counts.get("passed", 0),
            "failed": counts.get("failed", 0),
            "skipped": counts.get("skipped", 0),
        }

    # ── 兼容旧 DataStore API（ActionHandler 仍用这些） ──

    def store_data(self, device_name: str, variable: str, value: Any) -> None:
        """旧 DataStore.store_data() → 存入 variables 表 (namespace = devices.xxx)。

        类型会被自动检测并保持。
        """
        namespace = f"devices.{device_name}"
        self.set(f"devices.{device_name}.{variable}", value)
        self._store.set_var(self._session_id, namespace, variable, value)
        # 兼容：Constants 同时写入 constants.xxx（新系统用）
        if device_name == "Constants":
            self.set(f"constants.{variable}", value)
            self._store.set_var(self._session_id, "constants", variable, value)

    def get_data(self, device_name: str, variable: str = None) -> Any:
        """旧 DataStore.get_data()。

        如果 variable 为 None，返回整个 device namespace。
        """
        if variable:
            val = self.get(f"devices.{device_name}.{variable}")
            if val is not None:
                return val
            return self._store.get_var(
                self._session_id, f"devices.{device_name}", variable)
        # 返回整个 namespace
        val = self.get(f"devices.{device_name}")
        if val is not None:
            return val
        return self._store.get_namespace(
            self._session_id, f"devices.{device_name}")

    def get_constant(self, key: str, default: Any = None) -> Any:
        """旧 DataStore.get_constant()。"""
        val = self.get(f"constants.{key}")
        if val is not None:
            return val
        return self._store.get_var(
            self._session_id, "constants", key) or default

    def store_constant(self, key: str, value: Any) -> None:
        """写入常量。"""
        self.set(f"constants.{key}", value)
        self._store.set_var(self._session_id, "constants", key, value)

    def delete_data(self, device_name: str, variable: str = None) -> bool:
        """旧 DataStore.delete_data()。"""
        if variable:
            # 从内存删
            dev = self.get(f"devices.{device_name}")
            if isinstance(dev, dict) and variable in dev:
                del dev[variable]
            # 从 SQLite 删
            return self._store.delete_var(
                self._session_id, f"devices.{device_name}", variable)
        # 删整个 device
        self.set(f"devices.{device_name}", None)  # 标记为 None
        return self._store.delete_var(
            self._session_id, f"devices.{device_name}")

    def has_data(self, device_name: str, variable: str = None) -> bool:
        """旧 DataStore.has_data()。"""
        if variable:
            return self.get(f"devices.{device_name}.{variable}") is not None
        dev = self.get(f"devices.{device_name}")
        return isinstance(dev, dict) and len(dev) > 0

    # ── 快照 / 调试 ──

    def snapshot(self) -> dict:
        """深拷贝当前内存树。"""
        return json.loads(json.dumps(self._data))

    def __repr__(self) -> str:
        return f"<Context session={self._session_id}>"


_SENTINEL = object()
