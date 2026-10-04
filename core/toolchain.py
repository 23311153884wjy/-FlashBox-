"""
工具链管理：定位 adb / fastboot，找不到时引导下载官方 platform-tools。

查找顺序：
1. 程序自带 tools/platform-tools（推荐，绿色版随包携带）
2. 系统 PATH
3. 常见安装目录（Android Studio SDK、用户目录）
4. 在线下载（需联网，从 Google 官方地址拉取）
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from typing import List, Optional

from .executor import Runner

PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"

# Windows 常见位置
_COMMON_DIRS = [
    r"C:\platform-tools",
    r"C:\Android\platform-tools",
    os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools"),
    os.path.expandvars(r"%PROGRAMFILES%\Android\android-sdk\platform-tools"),
]


def app_dir() -> str:
    """程序根目录：开发模式取项目根，打包后取 exe 所在目录。"""
    if getattr(sys, "frozen", False):  # PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundled_bin_dir() -> str:
    """随包携带的工具目录。"""
    return os.path.join(app_dir(), "tools", "platform-tools")


def _is_executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def find_tool(name: str) -> Optional[str]:
    """按查找顺序定位 adb / fastboot 的可执行文件绝对路径。"""
    exe = f"{name}.exe" if os.name == "nt" else name

    for base in (bundled_bin_dir(), *_COMMON_DIRS):
        if not base:
            continue
        cand = os.path.join(base, exe)
        if _is_executable(cand):
            return cand

    which = shutil.which(name)
    if which:
        return which
    return None


class Toolchain:
    """持有 adb / fastboot 路径，并提供版本探测。"""

    def __init__(self):
        self.adb: Optional[str] = find_tool("adb")
        self.fastboot: Optional[str] = find_tool("fastboot")

    @property
    def bin_dir(self) -> Optional[str]:
        for p in (self.adb, self.fastboot):
            if p:
                return os.path.dirname(p)
        return None

    def status(self) -> dict:
        return {
            "adb": self.adb or "未找到",
            "fastboot": self.fastboot or "未找到",
            "adb_version": self._version(self.adb),
            "fastboot_version": self._version(self.fastboot),
            "ready": bool(self.adb and self.fastboot),
        }

    def _version(self, tool: Optional[str]) -> str:
        if not tool:
            return "-"
        r = Runner().run([tool, "version"], timeout=15)
        if r.ok:
            for line in r.output.splitlines():
                if line.strip():
                    return line.strip()
        return "未知"

    def refresh(self):
        self.adb = find_tool("adb")
        self.fastboot = find_tool("fastboot")

    def cmd(self, tool: str, args: List[str]) -> Optional[List[str]]:
        """拼出完整命令行；工具缺失时返回 None。"""
        path = getattr(self, tool, None)
        if not path:
            return None
        return [path, *args]


def download_platform_tools(dest_dir: str, on_progress=None) -> str:
    """
    下载并解压官方 platform-tools 到 dest_dir。

    依赖标准库 urllib，避免额外打包体积。返回解压后的目录。
    """
    import urllib.request

    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, "platform-tools.zip")

    def _hook(count, block, total):
        if on_progress and total:
            on_progress(min(100, int(count * block * 100 / total)))

    urllib.request.urlretrieve(PLATFORM_TOOLS_URL, zip_path, reporthook=_hook)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    os.remove(zip_path)

    extracted = os.path.join(dest_dir, "platform-tools")
    if not os.path.isdir(extracted):
        raise RuntimeError("解压后未找到 platform-tools 目录")
    return extracted
