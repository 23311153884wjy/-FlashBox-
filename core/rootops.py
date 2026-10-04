"""
Root 实操：模块 / KPM 的增删改查，以及修补刷入流程的命令生成。

模块机制要点：
  · 禁用 = 在模块目录放 disable 标记；移除 = 放 remove 标记；重启后生效
  · KernelSU 系（ksu / ksun / sukisu）从某版本起不再内置模块挂载，
    新装必须补一个 metamodule（meta-overlayfs / Meta-Hybrid Mount），否则模块不生效
  · APatch / FolkPatch 走 APM，KPM 走内核模块目录
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .executor import Runner
from .rootsol import RootSolution, module_ops

MAGISK_SU_PATHS = ["/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su"]


class RootOps:
    def __init__(self, adb: Optional[str], serial: Optional[str] = None):
        self.adb = adb
        self.serial = serial
        self.runner = Runner(timeout=90)

    def _base(self) -> List[str]:
        cmd = [self.adb or "adb"]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def sh(self, script: str, root: bool = True) -> Tuple[bool, str]:
        """在设备上执行 shell；root=True 时自动套 su -c。"""
        if not self.adb:
            return False, "未找到 adb"
        payload = f"su -c '{script}'" if root else script
        cmd = self._base() + ["shell", payload]
        r = self.runner.run(cmd)
        return r.ok, r.output

    # ---------- 状态 ----------

    def detect_root_impl(self) -> str:
        """判断当前是哪种 root 实现，返回 ksu / ksun / sukisu / apatch / magisk / none。"""
        checks = [
            ("ksu", "test -d /data/adb/ksu && echo 1"),
            ("apatch", "test -d /data/adb/ap && echo 1"),
            ("magisk", "test -d /data/adb/magisk && echo 1"),
        ]
        for tag, test in checks:
            ok, out = self.sh(test, root=True)
            if ok and "1" in out:
                return tag
        ok, out = self.sh("id")
        if ok and "uid=0" in out:
            return "unknown-root"
        return "none"

    def su_version(self) -> str:
        ok, out = self.sh("su -v")
        if ok and out.strip():
            return out.strip()
        ok, out = self.sh("su --version")
        return out.strip() if ok else "-"

    # ---------- 模块 ----------

    def list_modules(self, sol: RootSolution) -> List[dict]:
        """
        列出模块。返回 [{id, enabled, removed}]。
        """
        ok, out = self.sh(f"ls -1 {sol.module_dir}")
        if not ok or not out.strip():
            return []
        ids = [x.strip() for x in out.splitlines() if x.strip() and not x.startswith(".")]
        result = []
        for mid in ids:
            _, flags = self.sh(f"ls -1 {sol.module_dir}/{mid}")
            fl = flags or ""
            result.append({
                "id": mid,
                "enabled": "disable" not in fl,
                "removed": "remove" in fl,
            })
        return result

    def set_module_state(self, sol: RootSolution, module_id: str, op: str) -> Tuple[bool, str]:
        ops = module_ops(sol, module_id)
        if op not in ops:
            return False, f"不支持的操作：{op}"
        return self.sh(ops[op])

    def install_module(self, sol: RootSolution, local_zip: str, log=None) -> bool:
        """推送 zip 到设备并用对应管理器命令行安装。"""
        remote = f"/sdcard/Download/{local_zip.split('/')[-1].split(chr(92))[-1]}"
        cmd = self._base() + ["push", local_zip, remote]
        if log:
            log(f"$ {' '.join(cmd)}")
        r = self.runner.run(cmd)
        if log:
            log(r.output or "")
        if not r.ok:
            return False

        installers = {
            "kernelsu": "ksud module install",
            "apatch": "apd module install",
        }
        prefix = installers.get(sol.family, "ksud module install")
        ok, out = self.sh(f"{prefix} {remote}")
        if log:
            log(out or "")
        if not ok:
            # 命令行不可用则退回手动指引
            if log:
                log("[提示] 命令行安装失败，请打开管理器 App → 模块 → 从存储安装，选择手机内该文件")
        return ok

    # ---------- KPM ----------

    def list_kpm(self, sol: RootSolution) -> List[dict]:
        if not sol.kpm or not sol.kpm_dir:
            return []
        ok, out = self.sh(f"ls -1 {sol.kpm_dir}")
        if not ok or not out.strip():
            return []
        return [{"id": x.strip(), "loaded": True} for x in out.splitlines() if x.strip().endswith(".kpm")]

    def load_kpm(self, sol: RootSolution, local_kpm: str, log=None) -> bool:
        if not sol.kpm:
            return False
        remote = f"/sdcard/Download/{local_kpm.split('/')[-1].split(chr(92))[-1]}"
        cmd = self._base() + ["push", local_kpm, remote]
        if log:
            log(f"$ {' '.join(cmd)}")
        r = self.runner.run(cmd)
        if not r.ok:
            return False
        if sol.family == "kernelsu":
            ok, out = self.sh(f"ksud kpm load {remote}")
        else:
            ok, out = self.sh(f"apd kpm load {remote}")
        if log:
            log(out or "(已提交，重启后按管理器配置自动加载)")
        return ok

    def unload_kpm(self, sol: RootSolution, kpm_name: str) -> Tuple[bool, str]:
        if sol.family == "kernelsu":
            return self.sh(f"ksud kpm unload {kpm_name}")
        return self.sh(f"apd kpm unload {kpm_name}")


def patch_plan(sol: RootSolution, mode: str, has_init_boot: bool, android: str,
               img_path: str, serial: Optional[str] = None) -> List[dict]:
    """
    生成「修补 → 刷入」的完整步骤清单（供 UI 逐步展示与执行）。

    不代为下载镜像 —— 各方案的镜像必须从官方 Release 获取，工具只负责编排流程。
    """
    from .rootsol import choose_patch_partition

    part = choose_patch_partition(sol, mode, has_init_boot, android)
    steps: List[dict] = []

    steps.append({
        "title": f"① 备份原厂 {part}（强烈建议）",
        "cmd": "在工具箱『分区』页执行备份，或用管理器『直接安装』自动备份",
        "manual": True,
    })

    if sol.family == "kernelsu" and mode == "GKI":
        steps.append({
            "title": "② 获取与 KMI 一致的官方 GKI boot.img",
            "cmd": f"{sol.release}　（注意压缩格式需与原镜像一致：lz4 / gz / 不压缩）",
            "manual": True,
        })
        steps.append({
            "title": f"③ 临时引导验证（可选但推荐）",
            "cmd": f"fastboot boot {img_path or 'boot.img'}",
            "tool": "fastboot",
        })
    elif sol.family == "kernelsu":
        steps.append({
            "title": "② 用管理器修补官方固件（LKM 打 ramdisk）",
            "cmd": f"管理器 → 安装 → 选择文件 → 选中原厂 {part}.img → 生成 patched img",
            "manual": True,
        })
    else:  # apatch / fp
        steps.append({
            "title": "② 用管理器修补 boot.img（设置 SuperKey，事后不可更改）",
            "cmd": "管理器 → 修补 → 选中原厂 boot.img → 设定 SuperKey → 生成 patched img",
            "manual": True,
        })

    suffix = f" -s {serial}" if serial else ""
    steps.append({
        "title": f"④ 刷入修补后的镜像到 {part} 分区",
        "cmd": f"fastboot{suffix} flash {part} {img_path or 'patched.img'}",
        "tool": "fastboot",
    })
    steps.append({
        "title": "⑤ 重启并验证",
        "cmd": f"fastboot{suffix} reboot",
        "tool": "fastboot",
    })

    if sol.needs_metamodule:
        steps.append({
            "title": "⑥ 安装 metamodule（否则模块不生效）",
            "cmd": "管理器 → 模块 → 从存储安装 → meta-overlayfs 或 Meta-Hybrid Mount，重启",
            "manual": True,
        })

    steps.append({
        "title": "⑦ 失败回滚",
        "cmd": f"fastboot{suffix} flash {part} 原厂备份.img",
        "manual": True,
    })
    return steps


def parse_module_id(zip_path: str) -> str:
    """从模块 zip 文件名猜一个模块 id（仅用于显示）。"""
    name = re.split(r"[\\/]", zip_path)[-1]
    return re.sub(r"\.zip$", "", name)
