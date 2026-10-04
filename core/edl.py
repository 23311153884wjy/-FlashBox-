"""
深度刷机（救砖）支持：识别底层下载模式的 COM 口。

Windows 上通过 PowerShell 查询 PnP 设备；Linux 退化为扫描 /dev/tty*。
这里只做「识别 + 给指引 + 生成进入命令」，不代跑 QFIL / SP Flash Tool 等第三方工具。
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .executor import Runner

# 关键字 -> 平台判定
PORT_SIGNATURES = {
    "9008": ("高通 9008 / EDL", "qcom"),
    "QDLoader": ("高通 9008 / EDL", "qcom"),
    "HS-USB Diagnostics": ("高通 9008 / EDL", "qcom"),
    "HS-USB QDLoader": ("高通 9008 / EDL", "qcom"),
    "Qualcomm": ("高通（普通/9008 待确认）", "qcom"),
    "MT65xx PreLoader": ("联发科 PreLoader", "mtk"),
    "MediaTek PreLoader": ("联发科 PreLoader", "mtk"),
    "MediaTek USB Port": ("联发科 下载口", "mtk"),
    "MTK USB Port": ("联发科 下载口", "mtk"),
    "Spreadtrum": ("展锐 SPRD", "sprd"),
    "SPRD": ("展锐 SPRD", "sprd"),
    "SCI-USB": ("展锐 SPRD", "sprd"),
    "Rockusb": ("瑞芯微 Rockchip", "rk"),
    "Fastboot": ("Fastboot 接口", "fastboot"),
}

TOOL_GUIDE = {
    "qcom": [
        "QFIL / QPST（高通官方，需 firehose 编程器文件）",
        "edl.py / bkerler 的 edl 工具（开源，支持部分机型的 loader）",
        "厂商官方深度刷机工具（小米 MiFlash、一加 MSM、OPPO 深度刷机等）",
    ],
    "mtk": [
        "SP Flash Tool（联发科官方，需 scatter 文件 + DA）",
        "mtkclient（开源，支持绕过部分认证）",
        "厂商官方下载工具",
    ],
    "sprd": [
        "SPD Research Tool / 展锐下载工具（需 pac 固件）",
        "sprdclient（开源）",
    ],
    "rk": [
        "RKDevTool（瑞芯微官方，需 loader）",
        "rkdeveloptool（开源命令行）",
    ],
    "fastboot": ["当前是 Fastboot 接口，优先用常规 fastboot 线刷，无需进深度模式"],
}


@dataclass
class ComPort:
    device: str        # COM3 / /dev/ttyUSB0
    description: str
    platform: str

    def label(self) -> str:
        return f"{self.device}　{PORT_SIGNATURES.get(self.description.split('|')[0], (self.description,))[0]}"


def _scan_windows() -> List[ComPort]:
    ps = (
        "Get-WmiObject Win32_PnPEntity | "
        "Where-Object { $_.Name -match 'COM\\d+' } | "
        "Select-Object Name, DeviceID | Format-List"
    )
    try:
        r = Runner().run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            timeout=40,
        )
    except Exception:
        return []
    ports: List[ComPort] = []
    cur_name = ""
    for line in r.output.splitlines():
        line = line.strip()
        if line.startswith("Name"):
            cur_name = line.split(":", 1)[1].strip()
        elif line.startswith("DeviceID") or line.startswith("Device ID"):
            continue
        if not cur_name:
            continue
        m = re.search(r"COM(\d+)", cur_name)
        if not m:
            continue
        desc = cur_name
        plat = "unknown"
        for sig, (_label, p) in PORT_SIGNATURES.items():
            if sig.lower() in desc.lower():
                plat = p
                break
        ports.append(ComPort(f"COM{m.group(1)}", desc, plat))
        cur_name = ""
    return ports


def _scan_linux() -> List[ComPort]:
    ports: List[ComPort] = []
    for name in sorted(os.listdir("/dev")):
        if name.startswith(("ttyUSB", "ttyACM")):
            ports.append(ComPort(f"/dev/{name}", "USB 串口设备", "unknown"))
    return ports


def scan_ports() -> List[ComPort]:
    if platform.system() == "Windows":
        return _scan_windows()
    return _scan_linux()


def guide_for(platform_key: str) -> List[str]:
    return TOOL_GUIDE.get(platform_key, ["未识别平台，请根据机型搜索对应深度刷机工具"])


def edl_entry_commands() -> List[dict]:
    """进入 9008 / 下载模式的常见命令（按成功率排序）。"""
    return [
        {"label": "ADB：reboot edl（最通用）", "tool": "adb", "cmd": "adb reboot edl", "risk": "低"},
        {"label": "Fastboot：oem edl", "tool": "fastboot", "cmd": "fastboot oem edl", "risk": "中"},
        {"label": "Fastboot：reboot-edl", "tool": "fastboot", "cmd": "fastboot reboot-edl", "risk": "中"},
        {"label": "ADB：reboot-edl", "tool": "adb", "cmd": "adb reboot-edl", "risk": "低"},
        {"label": "Fastboot：oem reboot-edl", "tool": "fastboot", "cmd": "fastboot oem reboot-edl", "risk": "中"},
        {"label": "物理短接 / 主板测试点（终极手段）", "tool": "manual",
         "cmd": "拆机短接主板测试点，或按住特定组合键插入 USB", "risk": "高"},
    ]


def run_edl_command(adb: Optional[str], fastboot: Optional[str], item: dict, log=None) -> bool:
    if item["tool"] == "manual":
        if log:
            log("[提示] " + item["cmd"])
        return True
    binp = adb if item["tool"] == "adb" else fastboot
    if not binp:
        if log:
            log(f"[错误] 未找到 {item['tool']}")
        return False
    args = item["cmd"].split()[1:]
    cmd = [binp, *args]
    if log:
        log(f"$ {' '.join(cmd)}")
    r = Runner().run(cmd, timeout=60)
    if log:
        log(r.output or "(无输出，部分机型进入 EDL 后无回显)")
    return r.ok
