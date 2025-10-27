#!/usr/bin/env python3
"""
DataStore Manager - 管理和查询 AutoCom 数据存储

功能:
- 列出所有会话
- 查看特定会话的数据
- 跨会话查询变量
- 清理旧文件
- 导出数据
"""

import sys
import os
import json
import argparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from components.DataStore import DataStore
    from utils.common import CommonUtils
except ModuleNotFoundError:
    from ..components.DataStore import DataStore
    from .common import CommonUtils


def list_sessions(data_dir="temps/data_store", days=7):
    """列出所有会话"""
    sessions = DataStore.list_sessions(data_dir, days)
    
    if not sessions:
        print(f"No sessions found in the last {days} days")
        return
    
    print(f"\n{'='*80}")
    print(f"Found {len(sessions)} sessions in the last {days} days:")
    print(f"{'='*80}\n")
    
    for i, (session_id, filepath, file_time) in enumerate(sessions, 1):
        time_str = datetime.fromtimestamp(file_time).strftime("%Y-%m-%d %H:%M:%S")
        file_size = os.path.getsize(filepath)
        print(f"{i}. Session: {session_id}")
        print(f"   File: {filepath}")
        print(f"   Time: {time_str}")
        print(f"   Size: {file_size} bytes")
        print()


def view_session(session_id=None, filepath=None, data_dir="temps/data_store"):
    """查看特定会话的数据"""
    data = DataStore.load_session_data(session_id, filepath, data_dir)
    
    if not data:
        print(f"No data found for session: {session_id or filepath}")
        return
    
    print(f"\n{'='*80}")
    print(f"Session Data: {session_id or os.path.basename(filepath)}")
    print(f"{'='*80}\n")
    
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print()
    
    # Summary
    total_devices = len(data)
    total_variables = sum(len(variables) for variables in data.values())
    print(f"\nSummary: {total_devices} devices, {total_variables} variables")


def query_variable(device, variable, data_dir="temps/data_store", days=7):
    """跨会话查询变量"""
    results = DataStore.query_across_sessions(device, variable, data_dir, days)
    
    if not results:
        print(f"No data found for {device}.{variable} in the last {days} days")
        return
    
    print(f"\n{'='*80}")
    print(f"Query Results: {device}.{variable}")
    print(f"{'='*80}\n")
    
    for i, (session_id, value, timestamp) in enumerate(results, 1):
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{i}. [{time_str}] Session: {session_id}")
        print(f"   Value: {value}")
        print()
    
    print(f"Total: {len(results)} results found")


def cleanup_old_files(data_dir="temps/data_store", days=7, dry_run=False):
    """清理旧文件"""
    if not os.path.exists(data_dir):
        print(f"Directory not found: {data_dir}")
        return
    
    import glob
    import time as time_module
    
    current_time = time_module.time()
    cutoff_time = current_time - (days * 24 * 3600)
    
    pattern = os.path.join(data_dir, "session_*.json")
    files = glob.glob(pattern)
    
    to_delete = []
    for filepath in files:
        try:
            file_time = os.path.getmtime(filepath)
            if file_time < cutoff_time:
                to_delete.append((filepath, file_time))
        except Exception as e:
            print(f"Error checking file {filepath}: {e}")
    
    if not to_delete:
        print(f"No files older than {days} days found")
        return
    
    print(f"\n{'='*80}")
    print(f"{'DRY RUN - ' if dry_run else ''}Files to delete (older than {days} days):")
    print(f"{'='*80}\n")
    
    for filepath, file_time in to_delete:
        time_str = datetime.fromtimestamp(file_time).strftime("%Y-%m-%d %H:%M:%S")
        file_size = os.path.getsize(filepath)
        print(f"- {os.path.basename(filepath)}")
        print(f"  Time: {time_str}, Size: {file_size} bytes")
    
    print(f"\nTotal: {len(to_delete)} files")
    
    if not dry_run:
        confirm = input("\nAre you sure you want to delete these files? (yes/no): ")
        if confirm.lower() == 'yes':
            deleted_count = 0
            for filepath, _ in to_delete:
                try:
                    os.remove(filepath)
                    backup_file = f"{filepath}.backup"
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    deleted_count += 1
                except Exception as e:
                    print(f"Error deleting {filepath}: {e}")
            print(f"\nDeleted {deleted_count} files")
        else:
            print("Deletion cancelled")


def export_data(output_file, data_dir="temps/data_store", days=7):
    """导出所有会话数据到单个文件"""
    sessions = DataStore.list_sessions(data_dir, days)
    
    if not sessions:
        print(f"No sessions found in the last {days} days")
        return
    
    export_data = {}
    for session_id, filepath, file_time in sessions:
        data = DataStore.load_session_data(filepath=filepath)
        time_str = datetime.fromtimestamp(file_time).strftime("%Y-%m-%d %H:%M:%S")
        export_data[session_id] = {
            "timestamp": time_str,
            "data": data
        }
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(sessions)} sessions to: {output_file}")
    except Exception as e:
        print(f"Error exporting data: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="DataStore Manager - Manage and query AutoCom data storage",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all sessions")
    list_parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    list_parser.add_argument("--dir", default="temps/data_store", help="Data directory")
    
    # View command
    view_parser = subparsers.add_parser("view", help="View session data")
    view_parser.add_argument("session_id", help="Session ID to view")
    view_parser.add_argument("--dir", default="temps/data_store", help="Data directory")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query variable across sessions")
    query_parser.add_argument("device", help="Device name")
    query_parser.add_argument("variable", help="Variable name")
    query_parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    query_parser.add_argument("--dir", default="temps/data_store", help="Data directory")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old files")
    cleanup_parser.add_argument("--days", type=int, default=7, help="Delete files older than N days (default: 7)")
    cleanup_parser.add_argument("--dir", default="temps/data_store", help="Data directory")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export all sessions to a single file")
    export_parser.add_argument("output", help="Output file path")
    export_parser.add_argument("--days", type=int, default=7, help="Number of days to export (default: 7)")
    export_parser.add_argument("--dir", default="temps/data_store", help="Data directory")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "list":
        list_sessions(args.dir, args.days)
    elif args.command == "view":
        view_session(session_id=args.session_id, data_dir=args.dir)
    elif args.command == "query":
        query_variable(args.device, args.variable, args.dir, args.days)
    elif args.command == "cleanup":
        cleanup_old_files(args.dir, args.days, args.dry_run)
    elif args.command == "export":
        export_data(args.output, args.dir, args.days)


if __name__ == "__main__":
    main()
