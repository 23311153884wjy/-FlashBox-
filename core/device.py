"""
设备模型与检测：把 adb / fastboot 的原始输出解析成结构化信息。

连接模式：
  system    —— 开机进系统（adb 可用）
  recovery  ——  recovery（adb 可用）
  sideload  ——  recovery 的 sideload（adb 受限）
  fastboot  ——  bootloader（fastboot 可用）
  fastbootd ——  用户态 fastboot（Android 10+ 动态分区）
  edl       ——  高通 9008（不走 adb/fastboot，走串口）
  none      ——  没连上
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .executor import Runner


@dataclass
class Device:
    """一台已连接的设备。"""

    serial: str
    mode: str = "unknown"
    props: Dict[str, str] = field(default_factory=dict)

    # 常用字段的快捷访问
    @property
    def model(self) -> str:
        return self._pick("ro.product.model", "ro.product.device", "product")

    @property
    def codename(self) -> str:
        return self._pick("ro.product.device", "ro.product.board", "product")

    @property
    def android(self) -> str:
        return self.props.get("ro.build.version.release", "-")

    @property
    def kernel(self) -> str:
        return self.props.get("kernel.version", self.props.get("ro.kernel.version", "-"))

    @property
    def bootloader(self) -> str:
        return self.props.get("ro.bootloader", self.props.get("bootloader", "-"))

    @property
    def is_rooted(self) -> bool:
        return self.props.get("_root") == "1"

    @property
    def unlocked(self) -> Optional[bool]:
        v = self.props.get("ro.boot.flash.locked", self.props.get("unlocked"))
        if v is None:
            return None
        v = str(v).lower()
        if v in ("0", "no", "false"):
            return True  # locked=0 => 已解锁
        if v in ("1", "yes", "true"):
            return False
        return None

    @property
    def has_init_boot(self) -> bool:
        """Android 13+ 多为 init_boot 分区，决定 LKM 修补目标。"""
        return self.props.get("_has_init_boot") == "1"

    def _pick(self, *keys: str) -> str:
        for k in keys:
            v = self.props.get(k)
            if v:
                return v
        return "-"

    def summary(self) -> str:
        lock = {True: "已解锁", False: "未解锁", None: "未知"}[self.unlocked]
        return (
            f"型号：{self.model}\n"
            f"代号：{self.codename}\n"
            f"安卓：{self.android}　内核：{self.kernel}\n"
            f"Bootloader：{self.bootloader}（{lock}）\n"
            f"Root：{'已获取' if self.is_rooted else '无'}\n"
            f"模式：{self.mode}"
        )


MODE_LABEL = {
    "system": "系统（ADB）",
    "recovery": "Recovery（ADB）",
    "sideload": "Sideload",
    "fastboot": "Fastboot / Bootloader",
    "fastbootd": "Fastbootd（用户态）",
    "edl": "9008 / EDL",
    "unauthorized": "未授权（请在手机上点允许）",
    "offline": "离线（检查数据线与驱动）",
    "none": "未连接",
    "unknown": "未知",
}


def _parse_adb_devices(text: str) -> List[Device]:
    devices: List[Device] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if state == "device":
            devices.append(Device(serial, "system"))
        elif state == "recovery":
            devices.append(Device(serial, "recovery"))
        elif state == "sideload":
            devices.append(Device(serial, "sideload"))
        elif state == "unauthorized":
            devices.append(Device(serial, "unauthorized"))
        elif state == "offline":
            devices.append(Device(serial, "offline"))
    return devices


def _parse_fastboot_devices(text: str) -> List[Device]:
    devices: List[Device] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        serial = line.split()[0]
        mode = "fastbootd" if "fastbootd" in line.lower() else "fastboot"
        devices.append(Device(serial, mode))
    return devices


GETPROP_KEYS = [
    "ro.product.model",
    "ro.product.device",
    "ro.product.board",
    "ro.product.manufacturer",
    "ro.build.version.release",
    "ro.build.version.security_patch",
    "ro.bootloader",
    "ro.boot.flash.locked",
    "ro.boot.vbmeta.device_state",
    "ro.secure",
    "ro.debuggable",
    "persist.sys.usb.config",
]


class DeviceManager:
    """扫描并填充设备信息。"""

    def __init__(self, adb: Optional[str], fastboot: Optional[str]):
        self.adb = adb
        self.fastboot = fastboot
        self.runner = Runner(timeout=30)

    # ---------- 扫描 ----------

    def scan(self) -> List[Device]:
        devices: List[Device] = []
        if self.adb:
            r = self.runner.run([self.adb, "devices", "-l"])
            if r.ok:
                devices += _parse_adb_devices(r.output)
        if self.fastboot:
            r = self.runner.run([self.fastboot, "devices"])
            if r.ok:
                fb = _parse_fastboot_devices(r.output)
                known = {d.serial for d in devices}
                devices += [d for d in fb if d.serial not in known]
        return devices

    def enrich(self, dev: Device) -> Device:
        """尽量补全属性；fastboot 模式走 getvar，adb 模式走 getprop。"""
        if dev.mode in ("system", "recovery"):
            self._fill_by_getprop(dev)
        elif dev.mode in ("fastboot", "fastbootd"):
            self._fill_by_getvar(dev)
        return dev

    def _fill_by_getprop(self, dev: Device):
        if not self.adb:
            return
        keys = " ".join(GETPROP_KEYS)
        r = self.runner.run([self.adb, "-s", dev.serial, "shell", "getprop"] + GETPROP_KEYS)
        if not r.ok:
            # 老设备 getprop 多参数可能失败，退化为全量拉取再过滤
            r = self.runner.run([self.adb, "-s", dev.serial, "shell", "getprop"])
        for line in r.output.splitlines():
            m = re.match(r"\[(.+?)\]:\s*\[(.*)\]", line)
            if m and (m.group(1) in GETPROP_KEYS or not keys):
                dev.props[m.group(1)] = m.group(2)

        # Root 探测
        su = self.runner.run([self.adb, "-s", dev.serial, "shell", "su", "-c", "id"])
        dev.props["_root"] = "1" if su.ok and "uid=0" in su.output else "0"
        # KSU / APatch / Magisk 痕迹
        for path, tag in (
            ("/data/adb/ksu", "ksu"),
            ("/data/adb/ap", "apatch"),
            ("/data/adb/magisk", "magisk"),
            ("/data/adb/su", "sukisu"),
        ):
            t = self.runner.run([self.adb, "-s", dev.serial, "shell", f"test -d {path} && echo yes"])
            if "yes" in t.output:
                dev.props.setdefault("_root_impl", tag)
        # 分区探测（决定 boot / init_boot）
        for part in ("init_boot", "boot"):
            t = self.runner.run(
                [self.adb, "-s", dev.serial, "shell", f"test -e /dev/block/by-name/{part}_a && echo yes"]
            )
            if "yes" in t.output:
                dev.props["_has_init_boot"] = "1" if part == "init_boot" else "0"
                break
        # 内核版本
        kr = self.runner.run([self.adb, "-s", dev.serial, "shell", "uname", "-r"])
        if kr.ok and kr.output.strip():
            dev.props["kernel.version"] = kr.output.strip()

    def _fill_by_getvar(self, dev: Device):
        if not self.fastboot:
            return
        r = self.runner.run([self.fastboot, "-s", dev.serial, "getvar", "all"])
        for line in r.output.splitlines():
            m = re.match(r"(.+?):\s*(.*)", line)
            if m:
                dev.props[m.group(1).strip()] = m.group(2).strip()
        # 部分机型 getvar all 被禁用，退化为逐个查询
        if not dev.props:
            for var in ("product", "variant", "version-bootloader", "unlocked", "current-slot", "is-userspace"):
                r = self.runner.run([self.fastboot, "-s", dev.serial, "getvar", var])
                for line in r.output.splitlines():
                    m = re.match(rf"{var}:\s*(.*)", line)
                    if m:
                        dev.props[var] = m.group(1).strip()
        if dev.props.get("is-userspace") == "yes":
            dev.mode = "fastbootd"


def kmi_of(kernel: str) -> str:
    """从内核串里提取 KMI，如 6.1.57-android14-11 -> android14-6.1。"""
    if not kernel or kernel == "-":
        return "-"
    m = re.match(r"(\d+\.\d+)(?:\.\d+)?-(android\d+)-", kernel)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    return "-"
