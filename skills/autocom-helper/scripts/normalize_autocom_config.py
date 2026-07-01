#!/usr/bin/env python3
"""规范化 AutoCom Steps 格式配置的布局以提高可读性和一致性。"""

from __future__ import annotations

import argparse
import copy
import json
import os
from typing import Any, Dict, List

from lint_autocom_config import _load_config

TOP_KEYS = [
    "Config",
    "Devices",
    "Constants",
    "Steps",
    "loop",
]

DEVICE_KEYS = [
    "name",
    "status",
    "port",
    "baud_rate",
    "stop_bits",
    "parity",
    "data_bits",
    "flow_control",
    "dtr",
    "rts",
    "monitor",
]

STEP_KEYS = [
    "id",
    "name",
    "type",
    "device",
    "order",
    "send",
    "expect",
    "capture",
    "timeout",
    "url",
    "method",
    "headers",
    "body",
    "command",
    "shell",
    "duration",
    "target",
    "max_iterations",
    "if",
    "unless",
    "on_error",
    "on_success",
    "actions",
    "hex_mode",
]


def _ordered_obj(src: Dict[str, Any], preferred: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in preferred:
        if k in src:
            out[k] = src[k]
    for k in sorted(src.keys()):
        if k not in out:
            out[k] = src[k]
    return out


def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    cfg = copy.deepcopy(data)

    # 顶层键排序
    cfg = _ordered_obj(cfg, TOP_KEYS)

    # 设备排序
    devices = cfg.get("Devices")
    if isinstance(devices, list):
        norm_devices = []
        for dev in devices:
            if isinstance(dev, dict):
                norm_devices.append(_ordered_obj(dev, DEVICE_KEYS))
            else:
                norm_devices.append(dev)
        cfg["Devices"] = sorted(
            norm_devices,
            key=lambda d: (d.get("name", "") if isinstance(d, dict) else "")
        )

    # 步骤排序
    steps = cfg.get("Steps")
    if isinstance(steps, list):
        norm_steps = []
        for step in steps:
            if isinstance(step, dict):
                norm_steps.append(_ordered_obj(step, STEP_KEYS))
            else:
                norm_steps.append(step)

        def _step_sort_key(s: Any) -> Any:
            if not isinstance(s, dict):
                return (10 ** 9, "")
            order = s.get("order")
            if isinstance(order, int):
                return (order, s.get("id", ""))
            return (10 ** 9, s.get("id", ""))

        norm_steps.sort(key=_step_sort_key)
        cfg["Steps"] = norm_steps

    return cfg


def _dump(path: str, data: Dict[str, Any]) -> str:
    lower = path.lower()
    if lower.endswith(".json"):
        return json.dumps(data, indent=2, ensure_ascii=False)

    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("输出 YAML 文件需要 pyyaml 库，请执行: pip install pyyaml") from exc

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="规范化 AutoCom Steps 格式配置")
    parser.add_argument("file", help="源配置文件")
    parser.add_argument("--out", help="输出文件路径；默认: <输入文件名>.normalized.<扩展名>")
    parser.add_argument("--write", action="store_true", help="直接覆盖源文件")
    args = parser.parse_args()

    if args.write and args.out:
        print("错误: --write 和 --out 不能同时使用")
        return 2

    try:
        data = _load_config(args.file)
        normalized = _normalize(data)

        if args.write:
            target = args.file
        elif args.out:
            target = args.out
        else:
            root, ext = os.path.splitext(args.file)
            ext = ext or ".yaml"
            target = f"{root}.normalized{ext}"

        text = _dump(target, normalized)
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"已写入规范化配置到: {target}")
        return 0
    except Exception as e:
        print(f"错误: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())