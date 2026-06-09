#!/usr/bin/env python3
"""Normalize AutoCom config layout for readability and consistency."""

from __future__ import annotations

import argparse
import copy
import json
import os
from typing import Any, Dict, List

from lint_autocom_config import _load_config

TOP_KEYS = [
    "ConfigForDevices",
    "Devices",
    "ConfigForActions",
    "ConfigForCommands",
    "Constants",
    "Commands",
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

COMMAND_KEYS = [
    "command",
    "device",
    "order",
    "status",
    "expected_responses",
    "timeout",
    "concurrent_strategy",
    "success_actions",
    "error_actions",
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


def _normalize(data: Dict[str, Any], reindex_orders: bool = False) -> Dict[str, Any]:
    cfg = copy.deepcopy(data)

    # Top-level key ordering
    cfg = _ordered_obj(cfg, TOP_KEYS)

    # Devices ordering
    devices = cfg.get("Devices")
    if isinstance(devices, list):
        norm_devices = []
        for dev in devices:
            if isinstance(dev, dict):
                norm_devices.append(_ordered_obj(dev, DEVICE_KEYS))
            else:
                norm_devices.append(dev)
        # Stable sort by name when possible
        cfg["Devices"] = sorted(
            norm_devices,
            key=lambda d: (d.get("name", "") if isinstance(d, dict) else "")
        )

    # Commands ordering
    commands = cfg.get("Commands")
    if isinstance(commands, list):
        norm_cmds = []
        for cmd in commands:
            if isinstance(cmd, dict):
                norm_cmds.append(_ordered_obj(cmd, COMMAND_KEYS))
            else:
                norm_cmds.append(cmd)

        def _cmd_sort_key(c: Any) -> Any:
            if not isinstance(c, dict):
                return (10**9, "")
            order = c.get("order")
            if isinstance(order, int):
                return (order, c.get("device", ""))
            return (10**9, c.get("device", ""))

        norm_cmds.sort(key=_cmd_sort_key)

        if reindex_orders:
            for idx, cmd in enumerate(norm_cmds, start=1):
                if isinstance(cmd, dict):
                    cmd["order"] = idx

        cfg["Commands"] = norm_cmds

    return cfg


def _dump(path: str, data: Dict[str, Any]) -> str:
    lower = path.lower()
    if lower.endswith(".json"):
        return json.dumps(data, indent=2, ensure_ascii=False)

    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("pyyaml is required to write YAML files. install with: pip install pyyaml") from exc

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize AutoCom YAML/JSON config")
    parser.add_argument("file", help="source config file")
    parser.add_argument("--out", help="output file path; default: <input>.normalized.<ext>")
    parser.add_argument("--write", action="store_true", help="overwrite source file")
    parser.add_argument("--reindex-orders", action="store_true", help="rewrite command orders to 1..N after sort")
    args = parser.parse_args()

    if args.write and args.out:
        print("ERROR: --write and --out cannot be used together")
        return 2

    try:
        data = _load_config(args.file)
        normalized = _normalize(data, reindex_orders=args.reindex_orders)

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

        print(f"Wrote normalized config to: {target}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
