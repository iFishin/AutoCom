#!/usr/bin/env python3
"""
自动从 ActionHandler.py 提取 action 操作项并更新 Actions.md 文档

用法:
    python scripts/update_actions_doc.py
"""

import os
import re
import sys
from pathlib import Path


def extract_action_handlers():
    """从 ActionHandler.py 中提取所有 handle_* 方法及其文档"""
    
    # 找到 ActionHandler.py 的路径
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    handler_path = project_root / "utils" / "ActionHandler.py"
    
    if not handler_path.exists():
        print(f"错误: 找不到 {handler_path}")
        return None
    
    with open(handler_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 正则表达式：匹配 def handle_xxx 及其文档
    pattern = r'def (handle_\w+)\(.*?\):\s*"""(.*?)"""'
    matches = re.findall(pattern, content, re.DOTALL)
    
    actions = []
    for method_name, docstring in matches:
        # 跳过辅助方法
        if method_name in ['handle_actions', 'handle_response_actions', 'handle_variables_from_str']:
            continue
        
        # 提取 action 名称（去掉 handle_ 前缀）
        action_name = method_name[len('handle_'):]
        
        # 清理 docstring
        docstring_clean = docstring.strip()
        lines = docstring_clean.split('\n')
        
        # 提取说明（第一行或前两行）
        description = ""
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('{') and '用法' not in stripped:
                description = stripped
                break
        
        # 提取用法部分 - 从 "用法:" 开始，找到第一个完整的 JSON 对象
        usage_raw_lines = []  # 保留原始行（含缩进）
        found_usage_label = False
        brace_depth = 0
        
        for line in lines:
            # 查找 "用法:" 标记
            if '用法' in line and ':' in line:
                found_usage_label = True
                continue
            
            # 如果已开始查找用法且还没有达到顶层括号结束，继续收集
            if found_usage_label:
                stripped = line.strip()
                
                if not stripped:
                    # 空行可能表示 JSON 结束
                    if brace_depth == 0 and usage_raw_lines:
                        break
                    continue
                
                # 计算大括号深度
                for char in stripped:
                    if char == '{':
                        brace_depth += 1
                    elif char == '}':
                        brace_depth -= 1
                
                # 保存原始行
                usage_raw_lines.append(line)
                
                # 当返回到顶层括号（depth=0）且遇到 }
                if brace_depth == 0 and '}' in stripped and len(usage_raw_lines) > 0:
                    break
        
        # 处理缩进：找到最小的缩进，然后去除它
        if usage_raw_lines:
            # 计算最小缩进
            min_indent = float('inf')
            for raw_line in usage_raw_lines:
                if raw_line.strip():  # 忽略空行
                    indent = len(raw_line) - len(raw_line.lstrip())
                    min_indent = min(min_indent, indent)
            
            if min_indent == float('inf'):
                min_indent = 0
            
            # 移除最小缩进
            usage_lines = []
            for raw_line in usage_raw_lines:
                if raw_line.strip():
                    usage_lines.append(raw_line[min_indent:])
                else:
                    usage_lines.append(raw_line.rstrip())
            
            usage = '\n'.join(usage_lines)
        else:
            usage = f'{{"{action_name}": "..."}}'
        
        actions.append({
            'name': action_name,
            'description': description.strip(),
            'usage': usage,
            'full_docstring': docstring_clean
        })
    
    return actions


def generate_markdown_table(actions):
    """生成 Markdown 表格 - 简化格式"""
    
    markdown = "| Action | 格式 | 说明 |\n"
    markdown += "| :--- | :--- | :--- |\n"
    
    for action in actions:
        # 简化格式展示 - 只显示单行示例或格式概览
        action_name = action['name']
        
        # 根据 action 类型生成简化格式
        if action_name == 'test':
            format_str = '`{"test": "message"}`'
        elif action_name == 'save':
            format_str = '`{"save": {"device": "...", "variable": "...", "value": "..."}}`'
        elif action_name == 'save_conditional':
            format_str = '`{"save_conditional": {"device": "...", "variable": "...", "pattern": "..."}}`'
        elif action_name == 'retry':
            format_str = '`{"retry": 3}`'
        elif action_name == 'set_status':
            format_str = '`{"set_status": "enabled"}`'
        elif action_name == 'wait':
            format_str = '`{"wait": {"duration": 1000}}`'
        elif action_name == 'print':
            format_str = '`{"print": "message"}`'
        elif action_name == 'set_status_by_order':
            format_str = '`{"set_status_by_order": {"order": 2, "status": "..."}}`'
        elif action_name == 'execute_command':
            format_str = '`{"execute_command": {"command": "...", "timeout": 1000}}`'
        elif action_name == 'execute_command_by_order':
            format_str = '`{"execute_command_by_order": 3}`'
        elif action_name == 'generate_random_str':
            format_str = '`{"generate_random_str": {"device": "...", "variable": "...", "length": 100}}`'
        elif action_name == 'calculate_length':
            format_str = '`{"calculate_length": {"device": "...", "variable": "...", "data": "..."}}`'
        elif action_name == 'calculate_crc':
            format_str = '`{"calculate_crc": {"device": "...", "variable": "...", "raw_data": "..."}}`'
        elif action_name == 'replace_str':
            format_str = '`{"replace_str": {"device": "...", "variable": "...", "data": "...", "original_str": "...", "new_str": "..."}}`'
        elif action_name == 'wifi_connect':
            format_str = '`{"wifi_connect": {"ssid": "...", "password": "...", "timeout": 10}}`'
        elif action_name == 'get_wifi_config':
            format_str = '`{"get_wifi_config": {"device_ip": "...", "ssid": "...", "password": "..."}}`'
        elif action_name == 'get_network_page':
            format_str = '`{"get_network_page": {"device_ip": "...", "url": "/"}}`'
        elif action_name == 'send_file':
            format_str = '`{"send_file": "path/to/file.txt"}`'
        else:
            format_str = '`{...}`'
        
        # 简化描述
        descriptions = {
            'test': '测试功能',
            'save': '保存数据',
            'save_conditional': '条件保存数据',
            'retry': '重试指令',
            'set_status': '设置指令状态',
            'wait': '等待',
            'print': '打印消息',
            'set_status_by_order': '通过序号设置状态',
            'execute_command': '执行命令',
            'execute_command_by_order': '通过序号执行命令',
            'generate_random_str': '生成随机字符串',
            'calculate_length': '计算字符串长度',
            'calculate_crc': '计算 CRC 校验值',
            'replace_str': '字符串替换',
            'wifi_connect': '连接 WiFi',
            'get_wifi_config': '发送 WiFi 配置',
            'get_network_page': '获取网络页面',
            'send_file': '发送文件到设备'
        }
        
        description = descriptions.get(action_name, action['description'])
        
        markdown += f"| {action_name} | {format_str} | {description} |\n"
    
    return markdown


def generate_detailed_sections(actions):
    """生成详细说明部分 - 修复格式问题"""
    
    markdown = "## 详细说明\n\n"
    
    for action in actions:
        action_name = action['name']
        full_doc = action['full_docstring']
        
        # 从第一行获取简短描述
        first_line = full_doc.split('\n')[0].strip()
        
        markdown += f"### {action_name}\n\n"
        markdown += f"**说明:** {first_line}\n\n"
        
        # 提取用法部分（JSON）
        usage = action['usage']
        markdown += f"**格式:**\n```json\n{usage}\n```\n\n"
        
        # 提取参数说明
        params_match = re.search(r'参数[：:](.*?)(?=说明|返回|$)', full_doc, re.DOTALL)
        if params_match:
            params_text = params_match.group(1).strip()
            param_lines = [line.strip() for line in params_text.split('\n') if line.strip() and line.strip().startswith('-')]
            if param_lines:
                markdown += "**参数:**\n"
                for param_line in param_lines:
                    markdown += f"{param_line}\n"
                markdown += "\n"
        
        # 提取详细说明
        explain_match = re.search(r'说明[：:](.*?)(?=参数|返回|$)', full_doc, re.DOTALL)
        if explain_match:
            explanation = explain_match.group(1).strip()
            if explanation and not explanation.startswith('{'):
                markdown += f"**详细说明:**\n{explanation}\n\n"
        
        markdown += "---\n\n"
    
    return markdown


def update_actions_md(actions):
    """更新 Actions.md 文件"""
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    doc_path = project_root / "docs" / "Actions.md"
    
    # 生成表格部分
    quick_ref = generate_markdown_table(actions)
    
    # 生成详细说明部分
    detailed = generate_detailed_sections(actions)
    
    # 组织最终文档
    header = """# Actions 操作项

本文档自动生成自 `utils/ActionHandler.py`，记录所有可用的 action 操作项。

> 💡 **提示**: 此文档可通过脚本自动更新。运行 `python scripts/update_actions_doc.py` 来同步最新的 action 操作项定义。

## 快速参考表

"""
    
    full_content = header + quick_ref + "\n" + detailed
    
    # 写入文件
    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    return doc_path


def main():
    print("正在提取 ActionHandler 中的操作项...")
    actions = extract_action_handlers()
    
    if not actions:
        print("未找到任何 action 操作项")
        return 1
    
    print(f"找到 {len(actions)} 个 action 操作项:")
    for action in actions:
        print(f"  - {action['name']}")
    
    print("\n正在更新 Actions.md...")
    doc_path = update_actions_md(actions)
    
    print(f"✅ 成功更新: {doc_path}")
    print(f"共 {len(actions)} 个操作项已同步")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
