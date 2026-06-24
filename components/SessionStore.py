"""
AutoCom SessionStore — SQLite 持久化层

替代旧的 DataStore（JSON 快照），提供：
- ACID 事务（WAL 模式）
- 类型感知存储（int/float/bool/json 自动编解码）
- 按 session / step / variable / iteration 结构化查询
- 线程安全（threading.local() 每个线程独立连接）
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class SessionStore:
    """全局唯一的持久化层，所有数据读写走这里。"""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    # ── 连接管理（每个线程独立连接） ──

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def close(self):
        """关闭当前线程的连接。建议在进程退出前调用。"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ── Schema ──

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id             TEXT PRIMARY KEY,
                status         TEXT DEFAULT 'running',
                started_at     TEXT,
                finished_at    TEXT,
                config_name    TEXT,
                config_hash    TEXT,
                description    TEXT,
                summary        TEXT
            );

            CREATE TABLE IF NOT EXISTS step_results (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT NOT NULL REFERENCES sessions(id),
                step_id       TEXT NOT NULL,
                step_index    INTEGER,
                step_type     TEXT,
                status        TEXT,
                send          TEXT,
                response      TEXT,
                elapsed_ms    INTEGER,
                error         TEXT,
                captured      TEXT,
                logged_at     TEXT DEFAULT (datetime('now')),
                UNIQUE(session_id, step_id)
            );

            CREATE TABLE IF NOT EXISTS variables (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT NOT NULL REFERENCES sessions(id),
                namespace     TEXT NOT NULL,
                key           TEXT NOT NULL,
                value         TEXT,
                value_type    TEXT DEFAULT 'str',
                updated_at    TEXT DEFAULT (datetime('now')),
                UNIQUE(session_id, namespace, key)
            );

            CREATE TABLE IF NOT EXISTS iterations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT NOT NULL REFERENCES sessions(id),
                iteration     INTEGER NOT NULL,
                status        TEXT,
                passed_count  INTEGER DEFAULT 0,
                failed_count  INTEGER DEFAULT 0,
                started_at    TEXT,
                finished_at   TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_step_results_session
                ON step_results(session_id, step_index);
            CREATE INDEX IF NOT EXISTS idx_step_results_status
                ON step_results(session_id, status);
            CREATE INDEX IF NOT EXISTS idx_variables_lookup
                ON variables(session_id, namespace, key);
        """)
        self.conn.commit()

    # ── Sessions ──

    def create_session(self, session_id: str, config_name: str = "",
                       config_hash: str = "") -> dict:
        self.conn.execute(
            "INSERT INTO sessions(id, started_at, config_name, config_hash) "
            "VALUES(?, datetime('now'), ?, ?)",
            (session_id, config_name, config_hash))
        self.conn.commit()
        return {"id": session_id}

    def close_session(self, session_id: str, status: str = "completed",
                      summary: dict | None = None):
        self.conn.execute(
            "UPDATE sessions SET status=?, finished_at=datetime('now'), "
            "summary=? WHERE id=?",
            (status, json.dumps(summary or {}), session_id))
        self.conn.commit()

    def get_session(self, session_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 20,
                      status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM sessions"
        params: list[Any] = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def delete_session(self, session_id: str):
        """级联删除一个 session 及其所有关联数据。"""
        self.conn.execute("DELETE FROM iterations WHERE session_id=?", (session_id,))
        self.conn.execute("DELETE FROM variables WHERE session_id=?", (session_id,))
        self.conn.execute("DELETE FROM step_results WHERE session_id=?", (session_id,))
        self.conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self.conn.commit()

    # ── Step Results ──

    def save_step(self, session_id: str, *,
                  step_id: str,
                  step_index: int,
                  step_type: str,
                  status: str,
                  send: str = "",
                  response: str = "",
                  elapsed_ms: int = 0,
                  error: str = "",
                  capture: dict | None = None) -> None:
        self.conn.execute("""
            INSERT INTO step_results(
                session_id, step_id, step_index, step_type,
                status, send, response, elapsed_ms, error, captured)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(session_id, step_id) DO UPDATE SET
                status=excluded.status,
                step_index=excluded.step_index,
                response=excluded.response,
                elapsed_ms=excluded.elapsed_ms,
                error=excluded.error,
                captured=excluded.captured
        """, (session_id, step_id, step_index, step_type,
              status, send, response, elapsed_ms, error,
              json.dumps(capture or {})))
        self.conn.commit()

    def get_steps(self, session_id: str,
                  status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM step_results WHERE session_id=?"
        params: list[Any] = [session_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY step_index"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_step(self, session_id: str,
                 step_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM step_results WHERE session_id=? AND step_id=?",
            (session_id, step_id)).fetchone()
        return dict(row) if row else None

    def count_step_status(self, session_id: str) -> dict:
        """统计一个 session 中各种状态的步骤数量。"""
        rows = self.conn.execute("""
            SELECT status, COUNT(*) as cnt
            FROM step_results
            WHERE session_id=?
            GROUP BY status
        """, (session_id,)).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    # ── Variables ──

    @staticmethod
    def _cast(value: str, value_type: str):
        """从字符串还原为原始类型。"""
        if value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        elif value_type == "json":
            return json.loads(value)
        return value  # "str" 或其他

    @staticmethod
    def _type_name(value) -> str:
        """返回值的类型名称（用于 value_type 列）。"""
        t = type(value)
        if t is int:
            return "int"
        elif t is float:
            return "float"
        elif t is bool:
            return "bool"
        elif t in (dict, list):
            return "json"
        return "str"

    def set_var(self, session_id: str, namespace: str,
                key: str, value) -> None:
        vtype = self._type_name(value)
        value_str = json.dumps(value, ensure_ascii=False) if vtype == "json" else str(value)
        self.conn.execute("""
            INSERT INTO variables(session_id, namespace, key, value, value_type)
            VALUES(?,?,?,?,?)
            ON CONFLICT(session_id, namespace, key) DO UPDATE SET
                value=excluded.value,
                value_type=excluded.value_type,
                updated_at=datetime('now')
        """, (session_id, namespace, key, value_str, vtype))
        self.conn.commit()

    def get_var(self, session_id: str, namespace: str,
                key: str) -> Any:
        row = self.conn.execute(
            "SELECT value, value_type FROM variables "
            "WHERE session_id=? AND namespace=? AND key=?",
            (session_id, namespace, key)).fetchone()
        if row:
            return self._cast(row["value"], row["value_type"])
        return None

    def get_namespace(self, session_id: str,
                      namespace: str) -> dict:
        """读取整个 namespace 下所有变量，返回 {key: value}。"""
        rows = self.conn.execute(
            "SELECT key, value, value_type FROM variables "
            "WHERE session_id=? AND namespace=?",
            (session_id, namespace)).fetchall()
        return {r["key"]: self._cast(r["value"], r["value_type"]) for r in rows}

    def delete_var(self, session_id: str, namespace: str,
                   key: str | None = None) -> bool:
        if key:
            cur = self.conn.execute(
                "DELETE FROM variables WHERE session_id=? AND namespace=? AND key=?",
                (session_id, namespace, key))
        else:
            cur = self.conn.execute(
                "DELETE FROM variables WHERE session_id=? AND namespace=?",
                (session_id, namespace))
        self.conn.commit()
        return cur.rowcount > 0

    # ── Iterations ──

    def start_iteration(self, session_id: str,
                        iteration: int) -> dict:
        self.conn.execute(
            "INSERT INTO iterations(session_id, iteration, status, started_at) "
            "VALUES(?,?, 'running', datetime('now'))",
            (session_id, iteration))
        self.conn.commit()
        return {"session_id": session_id, "iteration": iteration}

    def finish_iteration(self, session_id: str, iteration: int,
                         status: str | None, passed: int, failed: int):
        self.conn.execute("""
            UPDATE iterations SET status=?, passed_count=?, failed_count=?,
                finished_at=datetime('now')
            WHERE session_id=? AND iteration=?
        """, (status, passed, failed, session_id, iteration))
        self.conn.commit()

    def get_iterations(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM iterations WHERE session_id=? ORDER BY iteration",
            (session_id,))
        return [dict(r) for r in rows]
