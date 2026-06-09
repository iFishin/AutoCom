#!/usr/bin/env python3
"""Batch lint AutoCom config files in a directory tree."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple

# Reuse single-file lint implementation
from lint_autocom_config import Finding, _lint, _load_config


def _collect_files(root: str) -> List[str]:
    matches: List[str] = []
    for base, _, files in os.walk(root):
        for name in files:
            lower = name.lower()
            if lower.endswith(".json") or lower.endswith(".yaml") or lower.endswith(".yml"):
                matches.append(os.path.join(base, name))
    return sorted(matches)


def _severity_rank(sev: str) -> int:
    return {"blocker": 0, "major": 1, "minor": 2}.get(sev, 9)


def _print_for_file(path: str, findings: List[Finding]) -> None:
    rel = path
    print(f"\n== {rel}")
    if not findings:
        print("  No findings")
        return

    for f in sorted(findings, key=lambda x: (_severity_rank(x.severity), x.code, x.location)):
        print(f"  [{f.severity.upper()}] {f.code} {f.location}: {f.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch lint AutoCom YAML/JSON configs")
    parser.add_argument("path", help="directory path to scan")
    parser.add_argument("--stop-on-error", action="store_true", help="stop at first parse error")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"ERROR: not a directory: {args.path}")
        return 2

    files = _collect_files(args.path)
    if not files:
        print("No config files found (.json/.yaml/.yml).")
        return 0

    total_files = 0
    total_findings = 0
    blockers = 0
    majors = 0
    parse_errors: List[Tuple[str, str]] = []

    for path in files:
        total_files += 1
        try:
            data = _load_config(path)
            findings = _lint(data)
            total_findings += len(findings)
            blockers += sum(1 for f in findings if f.severity == "blocker")
            majors += sum(1 for f in findings if f.severity == "major")
            _print_for_file(path, findings)
        except Exception as e:  # parse/load issues
            parse_errors.append((path, str(e)))
            print(f"\n== {path}\n  [ERROR] PARSE failed: {e}")
            if args.stop_on_error:
                break

    print("\n== Summary")
    print(f"  files: {total_files}")
    print(f"  findings: {total_findings}")
    print(f"  blockers: {blockers}")
    print(f"  majors: {majors}")
    print(f"  parse_errors: {len(parse_errors)}")

    if parse_errors:
        return 2
    if blockers > 0 or majors > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
