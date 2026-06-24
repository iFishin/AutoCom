"""
AutoCom TemplateEngine — 变量解析与条件评估

功能：
1. resolve(text, ctx) → str
   - {{ steps.check_fw.capture.version }} → 精确 dot-path 替换
   - {RSSI} → 模糊搜索（兼容旧语法）
   - {{ val | int }} → pipe 过滤器

2. evaluate(expr, ctx) → bool
   - 安全的条件评估：== != < > <= >= in not_in matches starts_with
   - 禁止 eval()，用有限的操作符白名单

用法：
    engine = TemplateEngine(ctx)
    text = engine.resolve("FW: {{ steps.check_fw.capture.version }}")
    ok = engine.evaluate("{{ steps.check_signal.capture.rssi }} < 20")
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from components.Context import Context


class TemplateEngine:
    """模板引擎：变量替换 + 条件判断。"""

    def __init__(self, ctx: Context):
        self._ctx = ctx

        # 注册内置 pipe 过滤器
        self._filters: dict[str, Callable] = {
            "int": int,
            "float": float,
            "str": str,
            "len": len,
            "upper": str.upper,
            "lower": str.lower,
            "trim": str.strip,
            "urlencode": self._urlencode,
            "json": self._to_json,
        }

    # ── 注册自定义过滤器 ──

    def register_filter(self, name: str, func: Callable) -> None:
        self._filters[name] = func

    # ── 变量替换 ──

    def resolve(self, text: str) -> str:
        """替换字符串中所有 {{ }} 和 { } 变量引用。"""
        if not isinstance(text, str):
            return text

        # 1. 新语法 {{ path | filter }}
        def _replace_exact(m):
            raw = m.group(1).strip()
            parts = [p.strip() for p in raw.split("|")]
            path = parts[0]
            value = self._path_resolve(path)
            if value is None:
                return m.group(0)  # 找不到保留原样
            # 应用 filters
            for fname in parts[1:]:
                fn = self._filters.get(fname)
                if fn:
                    try:
                        value = fn(value)
                    except (ValueError, TypeError):
                        pass  # 过滤失败跳过
            return str(value)

        text = re.sub(r"\{\{(.+?)\}\}", _replace_exact, text)

        # 2. 旧语法 {VAR} 模糊搜索
        for var in re.findall(r"\{([A-Za-z0-9_]+)\}", text):
            value = self._fuzzy_resolve(var)
            if value is not None:
                text = text.replace(f"{{{var}}}", str(value))

        return text

    def resolve_dict(self, d: dict) -> dict:
        """递归替换 dict 中所有字符串值的变量。"""
        out = {}
        for k, v in d.items():
            if isinstance(v, str):
                out[k] = self.resolve(v)
            elif isinstance(v, dict):
                out[k] = self.resolve_dict(v)
            elif isinstance(v, list):
                out[k] = [self.resolve_dict(i) if isinstance(i, dict)
                          else self.resolve(i) if isinstance(i, str)
                          else i for i in v]
            else:
                out[k] = v
        return out

    # ── 条件评估 ──

    def evaluate(self, expression: str) -> bool:
        """安全评估条件表达式。

        支持操作符（按优先级）：
            ==, !=, <, >, <=, >=
            contains, not_contains
            matches, not_matches
            starts_with, ends_with
            in, not_in
            and, or, not
        """
        if not isinstance(expression, str) or not expression.strip():
            return True  # 无条件的步默认执行

        resolved = self.resolve(expression)

        # 纯布尔值
        if resolved.lower() in ("true", "yes", "1"):
            return True
        if resolved.lower() in ("false", "no", "0"):
            return False

        # 操作符评估（从长到短匹配，避免 < 截胡 <=）
        resolved = resolved.strip()
        ops = [
            (" not_contains ", self._eval_not_contains),
            (" contains ", self._eval_contains),
            (" not_matches ", self._eval_not_matches),
            (" matches ", self._eval_matches),
            (" ends_with ", self._eval_ends_with),
            (" starts_with ", self._eval_starts_with),
            (" not in ", self._eval_not_in),
            (" in ", self._eval_in),
            ("<=", self._eval_lte),
            (">=", self._eval_gte),
            ("!=", self._eval_ne),
            ("==", self._eval_eq),
            ("<", self._eval_lt),
            (">", self._eval_gt),
        ]

        for op_sym, op_fn in ops:
            if op_sym in resolved:
                left, right = resolved.split(op_sym, 1)
                return op_fn(left.strip(), right.strip())

        # 纯表达式（如 "1" 是 True，空是 False）
        return bool(resolved.strip())

    # ── Dot-path 精确解析 ──

    def _path_resolve(self, path: str) -> Any:
        """解析 {{ steps.check_fw.capture.version }} 这类精确路径。"""
        # 纯数字/布尔字面量
        if path in ("true", "True"):
            return True
        if path in ("false", "False"):
            return False
        try:
            if "." in path:
                return float(path)
            return int(path)
        except (ValueError, TypeError):
            pass
        # 字符串字面量（引号包裹）
        if (path.startswith('"') and path.endswith('"')) or \
           (path.startswith("'") and path.endswith("'")):
            return path[1:-1]
        # Context 路径
        return self._ctx.get(path)

    # ── 模糊搜索（兼容旧语法 {VAR}） ──

    def _fuzzy_resolve(self, name: str) -> Optional[str]:
        """按优先级搜索变量：steps capture → constants → devices → session。"""
        ctx = self._ctx

        # 1. 搜所有 step 的 capture
        steps = ctx.get("steps", {})
        if isinstance(steps, dict):
            for step_id, data in steps.items():
                if isinstance(data, dict):
                    cap = data.get("capture", {})
                    if isinstance(cap, dict) and name in cap:
                        return str(cap[name])

        # 2. 搜 constants
        val = ctx.get(f"constants.{name}")
        if val is not None:
            return str(val)

        # 3. 搜所有 devices 下
        devices = ctx.get("devices", {})
        if isinstance(devices, dict):
            for dev_name, dev_data in devices.items():
                if isinstance(dev_data, dict) and name in dev_data:
                    return str(dev_data[name])

        # 4. 搜 session
        val = ctx.get(f"session.{name}")
        if val is not None:
            return str(val)

        return None

    # ── 比较器工具 ──

    @staticmethod
    def _parse_literal(s: str):
        """将字面量转为 Python 值。"""
        s = s.strip()
        if s.isdigit():
            return int(s)
        try:
            return float(s)
        except ValueError:
            pass
        if s in ("true", "True"):
            return True
        if s in ("false", "False"):
            return False
        # 引号包裹的字符串
        if (s.startswith('"') and s.endswith('"')) or \
           (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        return s

    @staticmethod
    def _parse_list(s: str) -> list:
        """解析 [1, 2, 3] 或 "a", "b" 形式的列表。"""
        s = s.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        items = []
        for part in s.split(","):
            item = part.strip()
            if item:
                items.append(TemplateEngine._parse_literal(item))
        return items

    @staticmethod
    def _cmp(a, b) -> int:
        """a < b → -1, a == b → 0, a > b → 1。支持跨类型。"""
        a = TemplateEngine._parse_literal(a)
        b = TemplateEngine._parse_literal(b)
        if isinstance(a, (int, float, bool)) and isinstance(b, (int, float, bool)):
            av = float(a)
            bv = float(b)
            return -1 if av < bv else 1 if av > bv else 0
        if isinstance(a, str) and isinstance(b, str):
            return -1 if a < b else 1 if a > b else 0

        sa = str(a)
        sb = str(b)
        return -1 if sa < sb else 1 if sa > sb else 0

    # ── 操作符实现 ──

    def _eval_eq(self, left, right):
        return self._cmp(left, right) == 0

    def _eval_ne(self, left, right):
        return self._cmp(left, right) != 0

    def _eval_lt(self, left, right):
        return self._cmp(left, right) < 0

    def _eval_gt(self, left, right):
        return self._cmp(left, right) > 0

    def _eval_lte(self, left, right):
        return self._cmp(left, right) <= 0

    def _eval_gte(self, left, right):
        return self._cmp(left, right) >= 0

    def _eval_in(self, left, right):
        item = self._parse_literal(left)
        lst = self._parse_list(right) if "," in right or right.strip().startswith("[") else [self._parse_literal(right)]
        return item in lst

    def _eval_not_in(self, left, right):
        return not self._eval_in(left, right)

    def _eval_contains(self, left, right):
        return str(self._parse_literal(right)) in str(self._parse_literal(left))

    def _eval_not_contains(self, left, right):
        return not self._eval_contains(left, right)

    def _eval_matches(self, left, right):
        try:
            return bool(re.search(str(self._parse_literal(right)),
                                   str(self._parse_literal(left))))
        except re.error:
            return False

    def _eval_not_matches(self, left, right):
        return not self._eval_matches(left, right)

    def _eval_starts_with(self, left, right):
        return str(self._parse_literal(left)).startswith(str(self._parse_literal(right)))

    def _eval_ends_with(self, left, right):
        return str(self._parse_literal(left)).endswith(str(self._parse_literal(right)))

    # ── Filters ──

    @staticmethod
    def _urlencode(s):
        import urllib.parse
        return urllib.parse.quote(str(s), safe="")

    @staticmethod
    def _to_json(s):
        return json.dumps(s, ensure_ascii=False)
