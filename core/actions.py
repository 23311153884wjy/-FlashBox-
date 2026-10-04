"""
ADB / Fastboot 命令封装。

设计原则（也是安全底线）：
  · 不默认带 -w（wipe），任何清数据操作必须用户显式点第二次确认
  · 破坏性操作（flash / erase / unlock）先在 UI 弹出命令预览
  · 优先用 fastboot boot 临时引导，确认能开机再永久刷入
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .executor import Runner


@dataclass
class Action:
    """一个可在 UI 上点击执行的操作。"""

    key: str
    label: str
    tool: str          # adb / fastboot
    args: List[str]
    destructive: bool = False
    confirm: str = ""
    tip: str = ""

    def command(self, bin_path: Optional[str], serial: Optional[str] = None) -> List[str]:
        base = [bin_path or self.tool]
        if serial:
            base += ["-s", serial]
        return base + self.args


# ---------------- ADB 动作 ----------------

ADB_ACTIONS: List[Action] = [
    Action("reboot", "重启到系统", "adb", ["reboot"], tip="普通重启"),
    Action("reboot_recovery", "重启到 Recovery", "adb", ["reboot", "recovery"]),
    Action("reboot_bootloader", "重启到 Bootloader", "adb", ["reboot", "bootloader"]),
    Action("reboot_fastbootd", "重启到 Fastbootd", "adb", ["reboot", "fastboot"],
           tip="Android 10+ 动态分区设备用这个进用户态 fastboot"),
    Action("reboot_edl", "重启到 9008 / EDL", "adb", ["reboot", "edl"],
           destructive=True, confirm="进入 9008 后设备黑屏无显示，仅能被 QFIL/QPST 等工具识别，确定继续？",
           tip="部分机型不支持该指令"),
    Action("root_shell", "获取 root shell 测试", "adb", ["shell", "su", "-c", "id"]),
    Action("screenshot", "截图到电脑", "adb", ["exec-out", "screencap", "-p"], tip="输出为 PNG 字节流"),
    Action("install", "安装 APK", "adb", ["install", "-r", "{file}"], tip="需选择 APK 文件"),
    Action("push", "推送文件到手机", "adb", ["push", "{file}", "/sdcard/"]),
    Action("pull", "从手机拉取文件", "adb", ["pull", "{remote}", "."]),
    Action("sideload", "Recovery 线刷更新包", "adb", ["sideload", "{file}"],
           tip="需设备处于 Recovery 的 Apply update / ADB sideload"),
]

# ---------------- Fastboot 动作 ----------------

FASTBOOT_ACTIONS: List[Action] = [
    Action("reboot", "重启到系统", "fastboot", ["reboot"]),
    Action("reboot_bootloader", "回到 Bootloader", "fastboot", ["reboot-bootloader"]),
    Action("reboot_recovery", "启动到 Recovery", "fastboot", ["reboot", "recovery"]),
    Action("getvar_all", "读取全部变量", "fastboot", ["getvar", "all"]),
    Action("slot", "查询当前槽位", "fastboot", ["getvar", "current-slot"]),
    Action("switch_slot", "切换到另一个槽位", "fastboot", ["--set-active={slot}"],
           destructive=True, confirm="切换 A/B 槽位可能导致无法启动，确定继续？"),
    Action("unlock", "解锁 Bootloader", "fastboot", ["flashing", "unlock"],
           destructive=True, confirm="解锁会清空整机数据并丧失保修（三星还会永久熔断 Knox），确定继续？"),
    Action("unlock_critical", "解锁 critical 分区", "fastboot", ["flashing", "unlock_critical"],
           destructive=True, confirm="解锁 critical 分区风险极高，确定继续？"),
    Action("lock", "重新上锁 Bootloader", "fastboot", ["flashing", "lock"],
           destructive=True, confirm="上锁前必须恢复完全官方固件，否则可能硬砖！确定继续？"),
    Action("erase_userdata", "清除 userdata", "fastboot", ["erase", "userdata"],
           destructive=True, confirm="将清空所有用户数据（不含内部存储的机型除外），确定继续？"),
    Action("erase_cache", "清除 cache", "fastboot", ["erase", "cache"],
           destructive=True, confirm="将清除 cache 分区，确定继续？"),
]


class Actions:
    """把动作真正跑起来。"""

    def __init__(self, adb: Optional[str], fastboot: Optional[str]):
        self.adb = adb
        self.fastboot = fastboot
        self.runner = Runner(timeout=300)

    def _bin(self, tool: str) -> Optional[str]:
        return self.adb if tool == "adb" else self.fastboot

    def run_action(self, action: Action, serial: Optional[str] = None, log=None) -> bool:
        binp = self._bin(action.tool)
        cmd = action.command(binp, serial)
        if binp is None:
            if log:
                log(f"[错误] 未找到 {action.tool}，请先在『工具箱』页配置 platform-tools")
            return False
        if log:
            log(f"$ {' '.join(str(c) for c in cmd)}")
        r = self.runner.run(cmd)
        if log:
            for line in r.output.splitlines():
                log(f"  {line}")
            log(f"[{'成功' if r.ok else f'失败 code={r.returncode}'}]")
        return r.ok

    # ---------- 常用组合流程 ----------

    def backup_partition(self, serial: Optional[str], partition: str, out_path: str, log=None) -> bool:
        """从设备当前 boot/init_boot 分区整分区拉出来做备份（需 root）。"""
        base = [self.adb or "adb"]
        if serial:
            base += ["-s", serial]
        dev_node = f"/dev/block/by-name/{partition}_a"
        cmd = base + ["shell", "su", "-c", f"dd if={dev_node} of=/sdcard/{partition}.img"]
        if log:
            log(f"$ {' '.join(cmd)}")
        r = self.runner.run(cmd)
        if log:
            log(r.output or "(无输出)")
        if not r.ok:
            # 退化为无 _a 后缀
            cmd = base + ["shell", "su", "-c", f"dd if=/dev/block/by-name/{partition} of=/sdcard/{partition}.img"]
            r = self.runner.run(cmd)
            if log:
                log(r.output or "(无输出)")
        if r.ok:
            pull = base + ["pull", f"/sdcard/{partition}.img", out_path]
            if log:
                log(f"$ {' '.join(pull)}")
            pr = self.runner.run(pull)
            if log:
                log(pr.output or "(无输出)")
            return pr.ok
        return False

    def flash_image(self, serial: Optional[str], partition: str, image: str, log=None,
                    disable_verity: bool = False) -> bool:
        """刷入镜像。vbmeta 相关自动附加去校验参数。"""
        base = [self.fastboot or "fastboot"]
        if serial:
            base += ["-s", serial]
        args = []
        if disable_verity:
            args += ["--disable-verity", "--disable-verification"]
        # vbmeta 自身需要用 --disable-verification 标记
        if partition == "vbmeta":
            base += ["--disable-verity", "--disable-verification"]
        cmd = base + args + ["flash", partition, image]
        if log:
            log(f"$ {' '.join(cmd)}")
        r = self.runner.run(cmd)
        if log:
            for line in r.output.splitlines():
                log(f"  {line}")
        return r.ok

    def temp_boot(self, serial: Optional[str], image: str, log=None) -> bool:
        """临时引导，不写入分区 —— 验证镜像可用性的最安全方式。"""
        base = [self.fastboot or "fastboot"]
        if serial:
            base += ["-s", serial]
        cmd = base + ["boot", image]
        if log:
            log(f"$ {' '.join(cmd)}　（临时引导，重启即恢复）")
        r = self.runner.run(cmd)
        if log:
            for line in r.output.splitlines():
                log(f"  {line}")
        return r.ok
