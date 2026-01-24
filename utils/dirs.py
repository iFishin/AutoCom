"""
autocom/dirs.py
路径管家：统一管理工作区目录 + 包资源目录
Python 3.7+ 通用，无需外部依赖（3.7/3.8 会自动用 importlib_resources 回退）
"""
from __future__ import annotations
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Final
from functools import lru_cache

# ---------- 跨版本 importlib.resources 兼容 ----------
if sys.version_info >= (3, 9):
    try:
        import importlib.resources as _res
        _files = _res.files
    except (ImportError, AttributeError):
        _files = None
else:
    _files = None

if _files is None:
    try:
        import importlib_resources as _res  # type: ignore
        _files = _res.files
    except ModuleNotFoundError:
        _files = None

# ---------- 内部辅助 ----------
def _package_dir() -> Path:
    """返回包安装目录（只读），兼容 __package__ 为 None"""
    if _files is not None:
        try:
            return Path(_files(__package__ or "autocom")).resolve()
        except (ValueError, TypeError):
            pass
    return Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def _ensure_dir(p: Path) -> Path:
    """原子级创建目录，可并发调用"""
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------- 路径管理类 ----------
class Dirs:
    """零配置、懒加载、可测试"""

    __slots__ = ("_root", "_pkg", "_session_dir")

    def __init__(self, root: Optional[Path] = None):
        self._root: Optional[Path] = root
        self._pkg: Path = _package_dir()
        self._session_dir: Optional[Path] = None

    # ========= 用户工作区（懒加载） =========
    @property
    def root(self) -> Path:
        if self._root is None:
            self._root = Path.cwd().resolve()
        return self._root

    @property
    def log_dir(self) -> Path:
        return _ensure_dir(self.root / "logs")

    @property
    def temp_dir(self) -> Path:
        return _ensure_dir(self.root / "temps")

    @property
    def data_store_dir(self) -> Path:
        return _ensure_dir(self.temp_dir / "data_store")

    @property
    def device_logs_dir(self) -> Path:
        return _ensure_dir(self.root / "device_logs")

    @property
    def dicts_dir(self) -> Path:
        return _ensure_dir(self.root / "dicts")

    @property
    def configs_dir(self) -> Path:
        return _ensure_dir(self.root / "configs")

    # ========= 包资源目录（只读） =========
    @property
    def package_dir(self) -> Path:
        return self._pkg

    @property
    def bundled_dicts_dir(self) -> Path:
        return self._pkg / "dicts"

    @property
    def bundled_configs_dir(self) -> Path:
        return self._pkg / "configs"
    
    @property
    def session_dir(self) -> Path:
        if self._session_dir is None:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self._session_dir = _ensure_dir(self.device_logs_dir / ts)
        return self._session_dir

    # ========= 便捷查询 + 初始化 =========
    def get_dict_path(self, name: str) -> Path:
        """优先本地工作区，其次包内；返回 Path（绝对）"""
        p = Path(name)
        if p.is_absolute():
            return p
        for base in (self.root, self.bundled_dicts_dir):
            candidate = base / name
            if candidate.exists():
                return candidate
        return self.root / name  # 不存在时仍返回本地路径（调用方决定报错）

    def get_config_path(self, name: str) -> Path:
        """同上，针对配置"""
        p = Path(name)
        if p.is_absolute():
            return p
        for base in (self.root, self.bundled_configs_dir):
            candidate = base / name
            if candidate.exists():
                return candidate
        return self.root / name

    def copy_examples(self) -> None:
        """把包内示例拷到用户工作区（不覆盖已存在）"""
        for src_dir, dst_name in (
            (self.bundled_dicts_dir, "dicts"),
            (self.bundled_configs_dir, "configs"),
        ):
            if not src_dir.exists():
                continue
            dst = self.root / dst_name
            dst.mkdir(parents=True, exist_ok=True)
            for item in src_dir.iterdir():
                dst_item = dst / item.name
                if dst_item.exists():
                    continue  # 不覆盖
                if item.is_dir():
                    shutil.copytree(item, dst_item)
                else:
                    shutil.copy2(item, dst_item)

    def init_project_structure(self) -> None:
        """一键创建基础目录 + 拷贝示例"""
        _ensure_dir(self.temp_dir)
        _ensure_dir(self.data_store_dir)
        _ensure_dir(self.device_logs_dir)
        _ensure_dir(self.dicts_dir)
        _ensure_dir(self.configs_dir)
        self.copy_examples()

# ---------- 进程单例 + 环境变量支持 ----------
@lru_cache(maxsize=1)
def get_dirs() -> Dirs:
    """全局唯一入口；支持环境变量 AUTOCOM_ROOT 换根"""
    root = None
    env_root = os.getenv("AUTOCOM_ROOT")
    if env_root:
        root = Path(env_root).resolve()
    return Dirs(root)


# 测试专用：强行换根
def set_dirs_root(root: Path) -> None:
    """仅用于单元测试，调用后 get_dirs() 返回新的根"""
    get_dirs.cache_clear()
    global _forced_instance
    _forced_instance = Dirs(root)

_forced_instance: Optional[Dirs] = None