#!/usr/bin/env python3
"""在 JSON 和 YAML 格式之间转换 AutoCom Steps 格式配置。"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

from lint_autocom_config import _load_config


def _target_path(src: str, to_fmt: str) -> str:
    root, _ = os.path.splitext(src)
    if to_fmt == "json":
        return f"{root}.json"
    return f"{root}.yaml"


def _serialize(data: Dict[str, Any], to_fmt: str) -> str:
    if to_fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)

    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("YAML 输出需要 pyyaml 库，请执行: pip install pyyaml") from exc

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="在 JSON 和 YAML 之间转换 AutoCom Steps 格式配置")
    parser.add_argument("file", help="源配置文件")
    parser.add_argument("--to", choices=["json", "yaml"], required=True, help="目标格式")
    parser.add_argument("--out", help="目标文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅显示目标路径，不实际写入")
    args = parser.parse_args()

    try:
        data = _load_config(args.file)
        out_path = args.out or _target_path(args.file, args.to)

        if args.dry_run:
            print(f"将写入: {out_path}")
            return 0

        text = _serialize(data, args.to)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"已转换 {args.file} -> {out_path}")
        return 0
    except Exception as e:
        print(f"错误: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())