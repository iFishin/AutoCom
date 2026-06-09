#!/usr/bin/env python3
"""Lint AutoCom config file (YAML/JSON) with portable checks.

This script is designed for standalone distribution with autocom-helper.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Finding:
    severity: str  # blocker | major | minor
    code: str
    message: str
    location: str


def _load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"file not found: {path}")

    lower = path.lower()
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if lower.endswith(".json"):
        data = json.loads(text)
    elif lower.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "pyyaml is required for YAML files. install with: pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
    else:
        # Try JSON first, then YAML
        try:
            data = json.loads(text)
        except Exception:
            try:
                import yaml  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "unknown file extension and pyyaml not installed. "
                    "use .json/.yaml or install pyyaml"
                ) from exc
            data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise ValueError("config root must be an object")
    return data


def _lint(data: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []

    devices = data.get("Devices")
    commands = data.get("Commands")
    constants = data.get("Constants", {})

    if not isinstance(devices, list) or not devices:
        findings.append(Finding("blocker", "E_DEV_001", "Devices must be a non-empty array", "Devices"))
        devices = []

    if not isinstance(commands, list) or not commands:
        findings.append(Finding("blocker", "E_CMD_001", "Commands must be a non-empty array", "Commands"))
        commands = []

    device_names: List[str] = []
    for idx, dev in enumerate(devices):
        if not isinstance(dev, dict):
            findings.append(Finding("blocker", "E_DEV_002", "Device item must be an object", f"Devices[{idx}]"))
            continue
        name = dev.get("name")
        if not isinstance(name, str) or not name.strip():
            findings.append(Finding("blocker", "E_DEV_003", "Device name is required", f"Devices[{idx}].name"))
            continue
        if name in device_names:
            findings.append(Finding("blocker", "E_DEV_004", f"Duplicate device name: {name}", f"Devices[{idx}].name"))
        else:
            device_names.append(name)

    orders_seen = set()
    constant_keys = set(constants.keys()) if isinstance(constants, dict) else set()

    for idx, cmd in enumerate(commands):
        loc = f"Commands[{idx}]"
        if not isinstance(cmd, dict):
            findings.append(Finding("blocker", "E_CMD_002", "Command item must be an object", loc))
            continue

        dev = cmd.get("device")
        if not isinstance(dev, str) or dev not in device_names:
            findings.append(Finding("blocker", "E_CMD_003", "Command.device must exist in Devices.name", f"{loc}.device"))

        order = cmd.get("order")
        if not isinstance(order, int):
            findings.append(Finding("blocker", "E_CMD_004", "Command.order must be an integer", f"{loc}.order"))
        else:
            if order in orders_seen:
                findings.append(Finding("major", "E_CMD_005", f"Duplicate order: {order}", f"{loc}.order"))
            orders_seen.add(order)

        exp = cmd.get("expected_responses")
        if not isinstance(exp, list) or not exp:
            findings.append(Finding("major", "E_CMD_006", "expected_responses should be a non-empty array", f"{loc}.expected_responses"))

        timeout = cmd.get("timeout")
        if isinstance(timeout, int) and timeout < 500:
            findings.append(Finding("minor", "E_CMD_007", "timeout may be too small (<500ms)", f"{loc}.timeout"))

        # Basic variable reference check: $VAR in command text
        text = cmd.get("command")
        if isinstance(text, str) and "$" in text:
            import re

            refs = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", text))
            undefined = sorted(r for r in refs if r not in constant_keys)
            if undefined:
                findings.append(
                    Finding(
                        "blocker",
                        "E_VAR_001",
                        f"undefined constants referenced: {', '.join(undefined)}",
                        f"{loc}.command",
                    )
                )

        # retry in success_actions is usually a smell
        sa = cmd.get("success_actions")
        if isinstance(sa, list):
            for aidx, action in enumerate(sa):
                if isinstance(action, dict) and "retry" in action:
                    findings.append(
                        Finding(
                            "major",
                            "E_ACT_001",
                            "retry should be placed in error_actions",
                            f"{loc}.success_actions[{aidx}]",
                        )
                    )

    return findings


def _print_findings(findings: List[Finding]) -> None:
    if not findings:
        print("No findings.")
        return

    order = {"blocker": 0, "major": 1, "minor": 2}
    findings = sorted(findings, key=lambda x: (order.get(x.severity, 9), x.code, x.location))

    for f in findings:
        print(f"[{f.severity.upper()}] {f.code} {f.location}: {f.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint AutoCom YAML/JSON config")
    parser.add_argument("file", help="path to config file")
    args = parser.parse_args()

    try:
        data = _load_config(args.file)
        findings = _lint(data)
        _print_findings(findings)

        has_bad = any(f.severity in {"blocker", "major"} for f in findings)
        return 1 if has_bad else 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
