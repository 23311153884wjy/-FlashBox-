"""打包前自动把官方 platform-tools 放到 tools/ 目录，让 exe 开箱即用。

单独跑：  python bootstrap_tools.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.toolchain import bundled_bin_dir, download_platform_tools  # noqa: E402


def main() -> int:
    dest = os.path.dirname(bundled_bin_dir())
    adb = os.path.join(bundled_bin_dir(), "adb.exe")

    if os.path.isfile(adb):
        print(f"[跳过] 已存在：{adb}")
        return 0

    print(f"[下载] 目标：{dest}")
    print("[下载] 来源：Google 官方 platform-tools")
    try:
        path = download_platform_tools(dest, lambda p: print(f"  {p}%", end="\r"))
    except Exception as exc:
        print(f"\n[失败] {exc}")
        print("可手动下载并解压到 tools/platform-tools：")
        print("  https://dl.google.com/android/repository/platform-tools-latest-windows.zip")
        return 1

    print(f"\n[完成] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
