"""
内核级 Root 方案定义。

覆盖五条主流路线：
  KSU        官方 KernelSU（LKM / GKI 双模式）
  KSUN       KernelSU-Next（更宽内核覆盖 + SUSFS 取向）
  SukiSU     SukiSU-Ultra（自带 KPM 支持）
  APatch     基于 KernelPatch，直接修补 boot.img，支持 KPM
  FP         FolkPatch（APatch 社区增强分支，模块仓库 / KPM 自动加载）

关键事实（决定工具怎么刷）：
  · LKM 模式改的是 ramdisk —— Android 13+ 打 init_boot，Android 12 及以下打 boot
  · GKI 模式整体替换内核   —— 永远打 boot，且压缩格式（lz4/gz/不压缩）必须与原镜像一致
  · APatch / FP 只修 boot.img，不需要内核源码
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RootSolution:
    key: str
    name: str
    family: str                 # kernelsu / apatch
    modes: List[str]            # 支持的修补模式
    manager_pkg: str            # 管理器包名
    repo: str
    release: str
    module_dir: str             # 模块目录（设备内）
    module_ext: List[str] = field(default_factory=lambda: [".zip"])
    kpm_dir: str = ""           # KPM 目录，空表示不支持
    kpm: bool = False
    needs_metamodule: bool = False
    patch_target: str = "auto"  # auto / boot / init_boot
    note: str = ""
    risk: str = ""

    def supports(self, mode: str) -> bool:
        return mode in self.modes

    def describe(self) -> str:
        lines = [
            f"方案：{self.name}（{self.family}）",
            f"模式：{' / '.join(self.modes)}",
            f"模块目录：{self.module_dir}",
        ]
        if self.kpm:
            lines.append(f"KPM 目录：{self.kpm_dir}")
        if self.needs_metamodule:
            lines.append("注意：KSU 已不再内置模块挂载，新装需先刷 meta-overlayfs 等 metamodule，否则模块装了不生效")
        if self.note:
            lines.append(self.note)
        if self.risk:
            lines.append(f"风险：{self.risk}")
        lines.append(f"仓库：{self.repo}")
        return "\n".join(lines)


SOLUTIONS: Dict[str, RootSolution] = {
    "ksu": RootSolution(
        key="ksu",
        name="KernelSU（官方）",
        family="kernelsu",
        modes=["LKM", "GKI"],
        manager_pkg="me.weishu.kernelsu",
        repo="https://github.com/tiann/KernelSU",
        release="https://github.com/tiann/KernelSU/releases",
        module_dir="/data/adb/modules",
        needs_metamodule=True,
        note="最小权限、安全第一；非 GKI 旧内核（4.x/3.x）官方不予支持。没有特殊需求优先官方版。",
        risk="刷错分区或压缩格式不一致会卡开机，务必先备份原厂 boot/init_boot。",
    ),
    "ksun": RootSolution(
        key="ksun",
        name="KernelSU-Next",
        family="kernelsu",
        modes=["LKM", "GKI"],
        manager_pkg="org.kernelsu.next",
        repo="https://github.com/rifsxd/KernelSU-Next",
        release="https://github.com/rifsxd/KernelSU-Next/releases",
        module_dir="/data/adb/modules",
        needs_metamodule=True,
        note="KSU 活跃分支：SUSFS 相关能力、更宽内核覆盖（含部分非 GKI）、更细授权规则。GKI 模式比官方强。",
        risk="分支方案攻击面更大，管理器与内核模块版本需匹配。",
    ),
    "sukisu": RootSolution(
        key="sukisu",
        name="SukiSU-Ultra",
        family="kernelsu",
        modes=["LKM", "GKI"],
        manager_pkg="me.sukisu.ultra",
        repo="https://github.com/SukiSU-Ultra/SukiSU-Ultra",
        release="https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases",
        module_dir="/data/adb/modules",
        kpm=True,
        kpm_dir="/data/adb/kpm",
        note="KSU 分支，自带 KPM 支持 + 内置 SUSFS，面向 Non-GKI 老内核做了大量 backport，开箱隐蔽性好。",
        risk="社区对其代码质量有争议；只从官方 Release 页下载。",
    ),
    "apatch": RootSolution(
        key="apatch",
        name="APatch（KernelPatch）",
        family="apatch",
        modes=["boot_patch"],
        manager_pkg="me.bmax.apatch",
        repo="https://github.com/bmax121/APatch",
        release="https://github.com/bmax121/APatch/releases",
        module_dir="/data/adb/modules",
        kpm=True,
        kpm_dir="/data/adb/kpm",
        patch_target="boot",
        note="不需要内核源码，直接反汇编修补预编译 kernel，只动 boot.img。原生 KPM（inline-hook / syscall-table-hook）。",
        risk="遇到特异内核、异常压缩格式可能修补失败，表现为卡第一屏。SuperKey 只在修补时设定，事后不可改。",
    ),
    "fp": RootSolution(
        key="fp",
        name="FolkPatch（APatch 分支）",
        family="apatch",
        modes=["boot_patch"],
        manager_pkg="io.github.folkpatch",
        repo="社区分支，请自行核对发布者身份后下载",
        release="社区分支，请自行核对发布者身份后下载",
        module_dir="/data/adb/modules",
        kpm=True,
        kpm_dir="/data/adb/kpm",
        patch_target="boot",
        note="APatch 增强分支：内置模块仓库、KPM 自动加载、主题商店等附加能力，自定义自由度极高。",
        risk="非官方主线，来源混杂，务必核对发布者身份，避免第三方镜像。",
    ),
}


def all_solutions() -> List[RootSolution]:
    return list(SOLUTIONS.values())


def get(key: str) -> RootSolution:
    return SOLUTIONS[key]


def choose_patch_partition(solution: RootSolution, mode: str, has_init_boot: bool, android: str = "") -> str:
    """
    决定该往哪个分区刷。

    LKM 改 ramdisk：Android 13+ 打 init_boot，12 及以下打 boot
    GKI / boot_patch：始终 boot
    """
    if solution.patch_target == "boot":
        return "boot"
    if mode == "GKI":
        return "boot"
    if mode == "LKM":
        if android:
            try:
                if float(android.split(".")[0]) >= 13:
                    return "init_boot"
            except ValueError:
                pass
        return "init_boot" if has_init_boot else "boot"
    return "boot"


# 各类 root 的模块启停标记文件
MODULE_DISABLE_FLAG = "disable"
MODULE_REMOVE_FLAG = "remove"


def module_ops(solution: RootSolution, module_id: str) -> Dict[str, str]:
    """生成模块目录内 enable / disable / remove 的 shell 片段。"""
    d = f"{solution.module_dir}/{module_id}"
    return {
        "enable": f"rm -f {d}/{MODULE_DISABLE_FLAG} {d}/{MODULE_REMOVE_FLAG}",
        "disable": f"touch {d}/{MODULE_DISABLE_FLAG}",
        "remove": f"touch {d}/{MODULE_REMOVE_FLAG}",
        "purge": f"rm -rf {d}",
    }
