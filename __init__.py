"""AutoCom - 自动化串口命令测试工具"""

from .version import __version__
from .AutoCom import (
    execute_with_loop,
    execute_with_folder,
    ensure_working_directories,
    monitor_folder,
    process_file_queue,
    load_commands_from_file,
)

__all__ = [
    '__version__',
    'execute_with_loop',
    'execute_with_folder',
    'ensure_working_directories',
    'monitor_folder',
    'process_file_queue',
    'load_commands_from_file',
]
