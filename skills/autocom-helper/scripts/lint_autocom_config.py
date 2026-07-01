#!/usr/bin/env python3
"""检查 AutoCom Steps 格式配置文件（YAML/JSON）的结构与语义。

此脚本设计为与 autocom-helper 技能一起独立分发使用。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List


VALID_TYPES = {"serial", "serial_wait", "http", "script", "wait", "action_batch", "goto"}
ON_ERROR_VALUES = {"abort", "skip"}
RE_RETRY = re.compile(r"^retry\((\d+)\)$")
RE_GOTO = re.compile(r"^goto\((.+)\)$")


@dataclass
class Finding:
    severity: str  # blocker | major | minor
    code: str
    message: str
    location: str


def _load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")

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
                "解析 YAML 需要 pyyaml 库，请执行: pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except Exception:
            try:
                import yaml  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "无法识别的文件扩展名且未安装 pyyaml。"
                    "请使用 .json/.yaml 扩展名或安装 pyyaml"
                ) from exc
            data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise ValueError("配置根节点必须是一个对象")
    return data


def _lint_steps(data: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []

    devices = data.get("Devices")
    steps = data.get("Steps")
    config = data.get("Config")
    constants = data.get("Constants", {})

    # ---- Devices 检查 ----
    if not isinstance(devices, list) or not devices:
        findings.append(Finding("blocker", "E_DEV_001", "Devices 必须是一个非空数组", "Devices"))
        devices = []
    device_names: List[str] = []
    for idx, dev in enumerate(devices):
        if not isinstance(dev, dict):
            findings.append(Finding("blocker", "E_DEV_002", "设备项必须是一个对象", f"Devices[{idx}]"))
            continue
        name = dev.get("name")
        if not isinstance(name, str) or not name.strip():
            findings.append(Finding("blocker", "E_DEV_003", "设备名称（name）是必填的", f"Devices[{idx}].name"))
            continue
        if name in device_names:
            findings.append(Finding("blocker", "E_DEV_004", f"重复的设备名称: {name}", f"Devices[{idx}].name"))
        else:
            device_names.append(name)

        port = dev.get("port")
        if not isinstance(port, str) or not port.strip():
            findings.append(Finding("blocker", "E_DEV_005", "设备端口（port）是必填的", f'Devices[{idx}].name="{name}"'))

    # ---- Steps 检查 ----
    if not isinstance(steps, list) or not steps:
        findings.append(Finding("blocker", "E_STEP_001", "Steps 必须是一个非空数组", "Steps"))
        steps = []

    step_ids: List[str] = []
    constant_keys = set(constants.keys()) if isinstance(constants, dict) else set()

    for idx, step in enumerate(steps):
        loc = f"Steps[{idx}]"
        if not isinstance(step, dict):
            findings.append(Finding("blocker", "E_STEP_002", "步骤项必须是一个对象", loc))
            continue

        sid = step.get("id")
        if not isinstance(sid, str) or not sid.strip():
            findings.append(Finding("blocker", "E_STEP_003", "步骤 id 是必填的", f"{loc}"))
        elif sid in step_ids:
            findings.append(Finding("blocker", "E_STEP_004", f"重复的步骤 id: {sid}", f"{loc}.id"))
        else:
            step_ids.append(sid)

        stype = step.get("type")
        if stype not in VALID_TYPES:
            findings.append(Finding("blocker", "E_STEP_005", f"无效的 type '{stype}'。有效值: {', '.join(sorted(VALID_TYPES))}", f"{loc}.type"))

        # 检查设备引用（serial/serial_wait 类型）
        dev_ref = step.get("device")
        if stype in ("serial", "serial_wait"):
            if not isinstance(dev_ref, str) or dev_ref not in device_names:
                findings.append(Finding("blocker", "E_STEP_006", f"步骤引用的设备 '{dev_ref}' 不在 Devices 列表中", f"{loc}.device"))

        # 检查 send 字段（serial 类型）
        if stype == "serial":
            send = step.get("send")
            if not isinstance(send, str) or not send.strip():
                findings.append(Finding("blocker", "E_STEP_007", "serial 步骤必须有非空的 send 字段", f"{loc}.send"))

        # 检查 expect
        expect = step.get("expect")
        if expect is not None:
            if stype == "serial":
                if not isinstance(expect, list) or not expect:
                    findings.append(Finding("major", "E_STEP_008", "serial 步骤的 expect 应为非空列表", f"{loc}.expect"))
            elif stype == "http":
                if not isinstance(expect, dict):
                    findings.append(Finding("major", "E_STEP_009", "http 步骤的 expect 应为对象（status_code / body_match）", f"{loc}.expect"))

        # 检查 timeout
        timeout = step.get("timeout")
        if isinstance(timeout, (int, float)):
            if timeout < 1:
                findings.append(Finding("minor", "E_STEP_010", f"timeout 似乎太小了 ({timeout}s)", f"{loc}.timeout"))

        # 检查 on_error
        on_err = step.get("on_error")
        if isinstance(on_err, str):
            if on_err in ON_ERROR_VALUES:
                pass  # 合法的字面值
            elif RE_RETRY.match(on_err):
                pass  # 合法的 retry(N)
            elif RE_GOTO.match(on_err):
                target = RE_GOTO.match(on_err).group(1)
                if target not in step_ids:
                    findings.append(Finding("blocker", "E_STEP_011", f"on_error 的 goto 目标 '{target}' 未在任何步骤 id 中找到", f"{loc}.on_error"))
            else:
                findings.append(Finding("major", "E_STEP_012", f"无效的 on_error 值: '{on_err}'。请使用 retry(N)、goto(id)、skip 或 abort", f"{loc}.on_error"))

        # 检查 on_success
        on_ok = step.get("on_success")
        if isinstance(on_ok, str):
            m = RE_GOTO.match(on_ok)
            if m:
                target = m.group(1)
                if target not in step_ids:
                    findings.append(Finding("blocker", "E_STEP_013", f"on_success 的 goto 目标 '{target}' 未在任何步骤 id 中找到", f"{loc}.on_success"))

        # 检查变量引用：{VAR} 格式
        for field_name in ("send", "url", "command"):
            val = step.get(field_name)
            if isinstance(val, str):
                refs = set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", val))
                undefined = sorted(r for r in refs if r not in constant_keys)
                if undefined:
                    findings.append(
                        Finding("blocker", "E_STEP_014", f"未定义的常量: {', '.join(undefined)}", f"{loc}.{field_name}")
                    )

        # 检查过时的 $VAR 语法
        for field_name in ("send", "url", "command"):
            val = step.get(field_name)
            if isinstance(val, str) and "$" in val:
                dollar_refs = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", val))
                if dollar_refs:
                    findings.append(
                        Finding("minor", "E_STEP_015", f"请使用 {{VAR}} 代替 $VAR: {', '.join(sorted(dollar_refs))}", f"{loc}.{field_name}")
                    )

        # 检查 goto 目标
        if stype == "goto":
            target = step.get("target")
            if not isinstance(target, str) or not target.strip():
                findings.append(Finding("blocker", "E_STEP_016", "goto 步骤必须有 target 字段", f"{loc}.target"))
            elif target not in step_ids:
                findings.append(Finding("blocker", "E_STEP_017", f"goto 目标 '{target}' 未在步骤 id 列表中找到", f"{loc}.target"))

    # ---- Config 检查 ----
    if isinstance(config, dict):
        loop = config.get("loop")
        if isinstance(loop, dict):
            dur = loop.get("duration")
            if isinstance(dur, str) and not re.match(r"^\d+[smh]$", dur):
                findings.append(Finding("minor", "E_CFG_001", f"duration 格式应为 '30s'、'5m'、'1h' 等，当前为 '{dur}'", "Config.loop.duration"))

    return findings


def _print_findings(findings: List[Finding]) -> None:
    if not findings:
        print("未发现问题。")
        return

    order = {"blocker": 0, "major": 1, "minor": 2}
    findings = sorted(findings, key=lambda x: (order.get(x.severity, 9), x.code, x.location))

    for f in findings:
        print(f"[{f.severity.upper()}] {f.code} {f.location}: {f.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 AutoCom Steps 格式配置（YAML/JSON）")
    parser.add_argument("file", help="配置文件路径")
    args = parser.parse_args()

    try:
        data = _load_config(args.file)
        findings = _lint_steps(data)
        _print_findings(findings)

        has_bad = any(f.severity in {"blocker", "major"} for f in findings)
        return 1 if has_bad else 0
    except Exception as e:
        print(f"错误: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())