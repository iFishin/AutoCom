#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
高性能可扩展 Logger 模块 for AutoCom
- 插件式着色系统
- 零开销日志级别检查
- 结构化上下文支持
- 类型安全
"""

import logging
import sys
import os
import re
import functools
import threading
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable, Pattern, Union, Protocol
from dataclasses import dataclass, field
from enum import Enum
from contextvars import ContextVar
from collections import defaultdict
from .TablePrinter import TablePrinter

# ============================================================================
# 类型定义
# ============================================================================


class ColorCode(Enum):
    """标准颜色代码"""

    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


class LogLevel(Enum):
    """日志级别枚举"""

    TRACE = 5
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    PASS = 25
    WARNING = logging.WARNING
    FAIL = 35
    ERROR = logging.ERROR
    FATAL = logging.FATAL
    CRITICAL = logging.CRITICAL


# 注册自定义级别
for level in LogLevel:
    if level.value not in logging._nameToLevel:
        logging.addLevelName(level.value, level.name)


# ============================================================================
# 着色器协议与注册表
# ============================================================================


class ColorizerProtocol(Protocol):
    """着色器协议 - 任何实现此协议的对象都可以作为着色器"""

    def can_handle(self, text: str) -> bool:
        """检查是否能处理该文本"""
        ...

    def colorize(self, text: str) -> str:
        """对文本进行着色"""
        ...


@dataclass
class RegexColorizer:
    """基于正则的着色器"""

    pattern: Union[str, Pattern]
    color: ColorCode
    group: int = 0  # 着色的捕获组

    def __post_init__(self):
        if isinstance(self.pattern, str):
            self.pattern = re.compile(self.pattern)
        elif not isinstance(self.pattern, re.Pattern):
            raise TypeError("pattern must be str or compiled regex Pattern")

    def can_handle(self, text: str) -> bool:
        if isinstance(self.pattern, str):
            return bool(re.search(self.pattern, text))
        return bool(self.pattern.search(text))

    def colorize(self, text: str) -> str:
        pattern = self.pattern
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
            self.pattern = pattern

        def replacer(match):
            full_match = match.group(0)
            if self.group == 0:
                target = full_match
            else:
                target = match.group(self.group)

            colored = f"{self.color.value}{target}{ColorCode.RESET.value}"
            return full_match.replace(target, colored) if self.group > 0 else colored

        return pattern.sub(replacer, text)


@dataclass
class KeywordColorizer:
    """基于关键词的着色器"""

    keywords: List[str]
    color: ColorCode
    case_sensitive: bool = False

    def __post_init__(self):
        if not self.case_sensitive:
            self.keywords = [k.lower() for k in self.keywords]

    def can_handle(self, text: str) -> bool:
        check_text = text if self.case_sensitive else text.lower()
        return any(kw in check_text for kw in self.keywords)

    def colorize(self, text: str) -> str:
        result = text
        for kw in self.keywords:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            pattern = re.compile(re.escape(kw), flags)
            result = pattern.sub(
                f"{self.color.value}\\g<0>{ColorCode.RESET.value}", result
            )
        return result


class ColorizerRegistry:
    """
    着色器注册表 - 管理所有着色器
    支持优先级、启用/禁用、热插拔
    """

    def __init__(self):
        self._colorizers: Dict[int, List[tuple]] = defaultdict(list)
        self._enabled: set = set()
        self._lock = threading.RLock()

    def register(
        self,
        colorizer: ColorizerProtocol,
        priority: int = 50,
        name: Optional[str] = None,
    ) -> str:
        """
        注册着色器

        Args:
            colorizer: 着色器实例
            priority: 优先级(0-100, 数字越小优先级越高)
            name: 着色器名称(可选)

        Returns:
            着色器ID
        """
        with self._lock:
            cid = name or f"colorizer_{id(colorizer)}"
            self._colorizers[priority].append((cid, colorizer))
            self._enabled.add(cid)
            return cid

    def unregister(self, cid: str) -> bool:
        """注销着色器"""
        with self._lock:
            for priority, colorizers in self._colorizers.items():
                for i, (id_, _) in enumerate(colorizers):
                    if id_ == cid:
                        colorizers.pop(i)
                        self._enabled.discard(cid)
                        return True
            return False

    def enable(self, cid: str) -> None:
        """启用着色器"""
        with self._lock:
            self._enabled.add(cid)

    def disable(self, cid: str) -> None:
        """禁用着色器"""
        with self._lock:
            self._enabled.discard(cid)

    def colorize(self, text: str) -> str:
        """按优先级应用所有启用的着色器"""
        result = text
        with self._lock:
            # 按优先级排序处理
            for priority in sorted(self._colorizers.keys()):
                for cid, colorizer in self._colorizers[priority]:
                    if cid in self._enabled and colorizer.can_handle(result):
                        result = colorizer.colorize(result)
        return result

    def clear(self) -> None:
        """清空所有着色器"""
        with self._lock:
            self._colorizers.clear()
            self._enabled.clear()


# ============================================================================
# 高性能 Formatter
# ============================================================================


class ExtensibleFormatter(logging.Formatter):
    """
    可扩展的高性能 Formatter
    - 支持插件式着色
    - 缓存颜色检测状态
    - 延迟格式化
    """

    # 类级缓存
    _color_support_cache: bool = False
    _cache_lock = threading.Lock()

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        color_registry: Optional[ColorizerRegistry] = None,
        force_color: Optional[bool] = None,
    ):
        super().__init__(fmt or "%(asctime)s - %(levelname)s - %(message)s", datefmt)

        self.registry = color_registry or ColorizerRegistry()
        self._force_color = force_color
        self._use_color = self._detect_color_support()

        # 预定义级别颜色(快速路径)
        self._level_colors = {
            "DEBUG": ColorCode.CYAN,
            "INFO": ColorCode.GREEN,
            "PASS": ColorCode.BRIGHT_GREEN,
            "WARNING": ColorCode.YELLOW,
            "FAIL": ColorCode.BRIGHT_RED,
            "ERROR": ColorCode.RED,
            "CRITICAL": ColorCode.BRIGHT_MAGENTA,
        }

    def _detect_color_support(self) -> bool:
        """检测是否支持颜色输出(带缓存)"""
        if self._force_color is not None:
            return self._force_color

        with self._cache_lock:
            if self._color_support_cache is None:
                self._color_support_cache = sys.stdout.isatty() or os.getenv(
                    "FORCE_COLOR", ""
                ).lower() in ("1", "true", "yes")
            return self._color_support_cache

    def format(self, record: logging.LogRecord) -> str:
        # 保存原始值
        original_levelname = record.levelname
        original_msg = record.msg

        try:
            # 级别着色(快速路径)
            if self._use_color and record.levelname in self._level_colors:
                color = self._level_colors[record.levelname]
                record.levelname = (
                    f"{color.value}{record.levelname}{ColorCode.RESET.value}"
                )

            # 消息着色(扩展路径)
            if self._use_color:
                record.msg = self.registry.colorize(str(record.msg))

            return super().format(record)

        finally:
            # 恢复原始值(避免污染其他handler)
            record.levelname = original_levelname
            record.msg = original_msg

    def add_colorizer(
        self,
        colorizer: ColorizerProtocol,
        priority: int = 50,
        name: Optional[str] = None,
    ) -> str:
        """便捷方法: 添加着色器"""
        return self.registry.register(colorizer, priority, name)


# ============================================================================
# 结构化上下文支持
# ============================================================================

# 上下文变量(线程/协程安全)
_log_context: ContextVar[Dict[str, Any]] = ContextVar("log_context", default={})


class LogContext:
    """
    结构化日志上下文管理器
    支持 with 语句和装饰器
    """

    def __init__(self, **kwargs):
        self.data = kwargs
        self._token = None

    def __enter__(self):
        current = _log_context.get().copy()
        current.update(self.data)
        self._token = _log_context.set(current)
        return self

    def __exit__(self, *args):
        if self._token:
            _log_context.reset(self._token)

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """获取上下文值"""
        return _log_context.get().get(key, default)

    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        """获取所有上下文"""
        return _log_context.get().copy()


def with_context(**ctx):
    """装饰器: 为函数添加日志上下文"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with LogContext(**ctx):
                return func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# 主 Logger 类
# ============================================================================


class AutoComLogger:
    """
    AutoCom 高性能日志器

    特性:
    - 单例模式 + 多实例支持
    - 零开销日志级别检查
    - 插件式着色系统
    - 结构化上下文
    - 异步安全
    """

    _instances: Dict[str, "AutoComLogger"] = {}
    _lock = threading.Lock()

    def __init__(
        self,
        name: str = "AutoCom",
        level: int = logging.DEBUG,
        log_file: Optional[str] = None,
        enable_color: bool = True,
        propagate: bool = False,
    ):
        self.name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.propagate = propagate

        # 清理旧handler(避免重复)
        self._logger.handlers.clear()

        # 创建注册表和formatter
        self._registry = ColorizerRegistry()
        self._formatter = ExtensibleFormatter(
            color_registry=self._registry,
            force_color=enable_color if enable_color else None,
        )

        # 添加控制台handler
        self._console_handler = logging.StreamHandler(sys.stdout)
        self._console_handler.setFormatter(self._formatter)
        self._logger.addHandler(self._console_handler)

        # 文件handler(可选)
        self._file_handler: Optional[logging.FileHandler] = None
        if log_file:
            self.set_log_file(log_file)

        # 注册默认着色器
        self._setup_default_colorizers()

        # TablePrinter实例
        self.tp = TablePrinter(
            headers=[
                "Executed Time",
                "Result",
                "Device",
                "Command",
                "Response",
                "Elapsed(ms)",
            ],
        )

    def _setup_default_colorizers(self) -> None:
        """设置默认着色规则 - 可扩展"""
        # 设备名着色 [DeviceName]
        self._registry.register(
            RegexColorizer(
                pattern=r"\[([^\]]+)\]", color=ColorCode.BRIGHT_BLUE, group=1
            ),
            priority=10,
            name="device_names",
        )

        # IP地址着色
        self._registry.register(
            RegexColorizer(
                pattern=r"\b(?:\d{1,3}\.){3}\d{1,3}\b", color=ColorCode.BRIGHT_CYAN
            ),
            priority=20,
            name="ip_addresses",
        )

        # 状态关键词着色
        self._registry.register(
            KeywordColorizer(
                keywords=["success", "成功"], color=ColorCode.BRIGHT_GREEN
            ),
            priority=30,
            name="success_keywords",
        )

        self._registry.register(
            KeywordColorizer(
                keywords=["failed", "失败", "error", "offline", "timeout"],
                color=ColorCode.BRIGHT_RED,
            ),
            priority=30,
            name="error_keywords",
        )

    @classmethod
    def get_instance(cls, name: str = "AutoCom", **kwargs) -> "AutoComLogger":
        """获取或创建命名实例(线程安全)"""
        with cls._lock:
            if name not in cls._instances:
                cls._instances[name] = cls(name=name, **kwargs)
            return cls._instances[name]

    def set_log_file(self, path: str, mode: str = "a") -> None:
        """设置日志文件"""
        if self._file_handler:
            self._logger.removeHandler(self._file_handler)

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        self._file_handler = logging.FileHandler(path, mode=mode, encoding="utf-8")
        # 文件不使用颜色
        self._file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self._logger.addHandler(self._file_handler)

    # ========================================================================
    # 核心日志方法(零开销检查)
    # ========================================================================

    def _log(self, level: int, msg: str, **kwargs) -> None:
        """内部日志方法(带上下文合并)"""
        if not self._logger.isEnabledFor(level):
            return

        # 合并上下文
        ctx = LogContext.get_all()
        if ctx:
            extra = kwargs.get("extra", {})
            extra["_context"] = ctx
            kwargs["extra"] = extra

        self._logger.log(level, msg, **kwargs)

    def log_debug(self, msg: str, **kwargs) -> None:
        """调试日志"""
        self._log(logging.DEBUG, msg, **kwargs)

    def log_info(self, msg: str, **kwargs) -> None:
        """信息日志"""
        self._log(logging.INFO, msg, **kwargs)

    def log_warning(self, msg: str, **kwargs) -> None:
        """警告日志"""
        self._log(logging.WARNING, msg, **kwargs)

    def log_error(self, msg: str, **kwargs) -> None:
        """错误日志"""
        self._log(logging.ERROR, msg, **kwargs)

    def log_critical(self, msg: str, **kwargs) -> None:
        """严重错误日志"""
        self._log(logging.CRITICAL, msg, **kwargs)

    def log_pass(self, msg: str, **kwargs) -> None:
        """成功/通过日志(自定义级别)"""
        self._log(LogLevel.PASS.value, msg, **kwargs)

    def log_fail(self, msg: str, **kwargs) -> None:
        """失败日志(自定义级别)"""
        self._log(LogLevel.FAIL.value, msg, **kwargs)

    ## 实时表格相关日志方法
    def log_realtime_table_header(self, headers: List[str]) -> None:
        """日志表格头部"""
        self.tp.headers = headers
        self.tp.print_realtime_header()

    def log_realtime_table_row(self, row: List[Any]) -> None:
        """日志表格行"""
        self.tp.print_realtime_row(row, is_print=True)

    def log_realtime_table_banner(self, text: str) -> None:
        """日志表格横幅"""
        self.tp.print_realtime_banner(text)

    def log_realtime_table_footer(self) -> None:
        """日志表格底部(结束)"""
        self.tp.print_realtime_footer()

    ## CLI 迭代日志方法
    def log_step_info(self, step_text: str) -> None:
        """Log step information"""
        self.log_realtime_table_banner(step_text)

    def log_step_success(self, step_text: str) -> None:
        """Log step success"""
        self.log_realtime_table_banner(f"✅ {step_text}")

    def log_step_error(self, step_text: str) -> None:
        """Log step error"""
        self.log_realtime_table_banner(f"❌ {step_text}")

    def log_step_warning(self, step_text: str) -> None:
        """Log step warning"""
        self.log_realtime_table_banner(f"⚠️ {step_text}")

    def log_iteration_start(self, iteration: int, total: int) -> None:
        """Log iteration start"""
        self.log_realtime_table_banner(f"ℹ Starting iteration {iteration}/{total}")

    def log_iteration_end(self, iteration: int, total: int) -> None:
        """Log iteration end summary"""
        self.log_realtime_table_banner(f"ℹ Finished iteration {iteration}/{total}")

    def log_session_start(self, session_text: str) -> None:
        """Log session header"""
        self.log_realtime_table_banner(f"{session_text}")

    def log_session_end(self, session_text: str) -> None:
        """Log session footer"""
        self.log_realtime_table_banner(f"{session_text}")

    def log_execution(
        self, result: bool, exec_type: str = "command", **kwargs: Any
    ) -> None:
        """
        Log command execution result with structured context

        Args:
            result: Execution result (True for PASS, False for FAIL)
            exec_type: Type of execution (e.g., "command", "api_call")
            kwargs: Additional context (e.g., device, command, response, elapsed_ms)
            Expected kwargs:
                - time_str: Timestamp
                - device: Device name
                - command: Command executed
                - response: Response message
                - elapsed_ms: Elapsed time in milliseconds

        """
        device = kwargs.get("device", "UnknownDevice")
        command = kwargs.get("command", "UnknownCommand")
        response = kwargs.get("response", "")
        elapsed_ms = kwargs.get("elapsed_ms", 0.0)
        self.log_realtime_table_row(
            [
                kwargs.get("time_str", ""),
                "✅PASS" if result else "❌FAIL",
                device,
                command,
                repr(response),
                f"{elapsed_ms:.2f}",
            ],
        )

    # ========================================================================
    # 扩展功能
    # ========================================================================

    def add_colorizer(
        self,
        pattern: Union[str, Pattern],
        color: ColorCode,
        priority: int = 50,
        name: Optional[str] = None,
        colorizer_class: type = RegexColorizer,
    ) -> str:
        """
        便捷方法: 添加正则着色规则

        Example:
            logger.add_colorizer(
                pattern=r'\bAPI\b',
                color=ColorCode.BRIGHT_YELLOW,
                priority=10,
                name="api_highlight"
            )
        """
        colorizer = colorizer_class(pattern=pattern, color=color)
        return self._registry.register(colorizer, priority, name)

    def remove_colorizer(self, name: str) -> bool:
        """移除着色规则"""
        return self._registry.unregister(name)

    def bind(self, **ctx) -> "BoundLogger":
        """创建绑定上下文的子日志器"""
        return BoundLogger(self, ctx)

    @property
    def registry(self) -> ColorizerRegistry:
        """访问着色器注册表(高级用法)"""
        return self._registry


class BoundLogger:
    """绑定上下文的日志器代理"""

    def __init__(self, parent: AutoComLogger, context: Dict[str, Any]):
        self._parent = parent
        self._context = context

    def _merge_kwargs(self, kwargs: Dict) -> Dict:
        """合并上下文到kwargs"""
        extra = kwargs.get("extra", {})
        extra.update(self._context)
        kwargs["extra"] = extra
        return kwargs

    def log_debug(self, msg: str, **kwargs) -> None:
        self._parent.log_debug(msg, **self._merge_kwargs(kwargs))

    def log_info(self, msg: str, **kwargs) -> None:
        self._parent.log_info(msg, **self._merge_kwargs(kwargs))

    def log_warning(self, msg: str, **kwargs) -> None:
        self._parent.log_warning(msg, **self._merge_kwargs(kwargs))

    def log_error(self, msg: str, **kwargs) -> None:
        self._parent.log_error(msg, **self._merge_kwargs(kwargs))

    def log_pass(self, msg: str, **kwargs) -> None:
        self._parent.log_pass(msg, **self._merge_kwargs(kwargs))

    def log_fail(self, msg: str, **kwargs) -> None:
        self._parent.log_fail(msg, **self._merge_kwargs(kwargs))


# ============================================================================
# 便捷函数
# ============================================================================


def get_logger(name: str = "AutoCom") -> AutoComLogger:
    """获取默认日志器实例"""
    return AutoComLogger.get_instance(name)


def setup_root_logger(
    level: int = logging.INFO, log_file: Optional[str] = None, enable_color: bool = True
) -> AutoComLogger:
    """配置根日志器"""
    return AutoComLogger.get_instance(
        "AutoCom", level=level, log_file=log_file, enable_color=enable_color
    )


# ============================================================================
# 使用示例与测试
# ============================================================================

if __name__ == "__main__":
    # 基础用法
    logger = get_logger()

    logger.log_info("系统启动完成")
    logger.log_pass("[Device-A] 连接成功")
    logger.log_fail("[Device-B] 连接超时")
    logger.log_error("192.168.1.1 无法访问")

    # 添自定义着色规则
    logger.add_colorizer(
        pattern=r"\bTODO\b",
        color=ColorCode.BRIGHT_YELLOW,
        priority=5,
        name="todo_highlight",
    )

    logger.log_info("TODO: 实现断点续传功能")

    # 使用上下文
    with LogContext(request_id="req-123", user="admin"):
        logger.log_info("处理请求中...")

        # 绑定上下文创建子日志器
        child = logger.bind(module="network")
        child.log_info("网络模块初始化")

    # 装饰器用法
    @with_context(task="data_sync")
    def sync_data():
        logger.log_info("开始数据同步")

    sync_data()
