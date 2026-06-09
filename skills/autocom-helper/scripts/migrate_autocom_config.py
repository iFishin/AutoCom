#!/usr/bin/env python3
"""Migrate AutoCom config between JSON and YAML formats."""

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
        raise RuntimeError("pyyaml is required for YAML output. install with: pip install pyyaml") from exc

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert AutoCom config between JSON and YAML")
    parser.add_argument("file", help="source config file")
    parser.add_argument("--to", choices=["json", "yaml"], required=True, help="target format")
    parser.add_argument("--out", help="target file path")
    parser.add_argument("--dry-run", action="store_true", help="only show target path, do not write")
    args = parser.parse_args()

    try:
        data = _load_config(args.file)
        out_path = args.out or _target_path(args.file, args.to)

        if args.dry_run:
            print(f"Would write: {out_path}")
            return 0

        text = _serialize(data, args.to)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"Converted {args.file} -> {out_path}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
