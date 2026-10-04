"""
命令执行器：封装 subprocess，统一处理中文编码、超时、取消。

这一层刻意不依赖 Qt，方便单测与命令行调用。
"""
from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# Windows 下隐藏子进程控制台窗口
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class CmdResult:
    """一条命令的执行结果。"""

    cmd: List[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """合并输出，CI 与人工阅读都方便。"""
        return (self.stdout + self.stderr).strip()


def build_env(extra_path: Optional[str] = None) -> dict:
    """构造子进程环境，可选把工具目录前置到 PATH。"""
    env = os.environ.copy()
    if extra_path and os.path.isdir(extra_path):
        env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")
    # 让 adb/fastboot 输出英文，解析更稳
    env.setdefault("LANG", "C")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class Runner:
    """
    同步/异步命令执行。

    异步方式通过 `run_stream` 起一个后台线程，把每行输出回调出去，
    同时返回句柄供取消 —— GUI 用来做实时日志。
    """

    def __init__(self, bin_dir: Optional[str] = None, timeout: int = 120):
        self.bin_dir = bin_dir
        self.timeout = timeout

    def _spawn(self, cmd: List[str], timeout: Optional[int] = None):
        env = build_env(self.bin_dir)
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_CREATE_NO_WINDOW,
        )

    def run(self, cmd: List[str], timeout: Optional[int] = None) -> CmdResult:
        """阻塞执行，返回完整结果。"""
        timeout = timeout if timeout is not None else self.timeout
        try:
            proc = self._spawn(cmd)
        except FileNotFoundError:
            return CmdResult(cmd, 127, "", f"找不到可执行文件: {cmd[0]}")
        except OSError as exc:  # 权限、路径异常等
            return CmdResult(cmd, 126, "", f"无法启动进程: {exc}")

        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return CmdResult(cmd, -1, "", f"执行超时（{timeout}s）")

        return CmdResult(cmd, proc.returncode, out or "", "")

    def run_stream(
        self,
        cmd: List[str],
        on_line: Callable[[str], None],
        timeout: Optional[int] = None,
    ) -> CmdResult:
        """流式执行，每行输出即时回调（用于实时日志窗）。"""
        timeout = timeout if timeout is not None else self.timeout
        lines: List[str] = []
        try:
            proc = self._spawn(cmd)
        except FileNotFoundError:
            on_line(f"[错误] 找不到可执行文件: {cmd[0]}")
            return CmdResult(cmd, 127, "", f"找不到可执行文件: {cmd[0]}")
        except OSError as exc:
            on_line(f"[错误] 无法启动进程: {exc}")
            return CmdResult(cmd, 126, "", str(exc))

        def _pump():
            try:
                for line in iter(proc.stdout.readline, ""):
                    if not line:
                        break
                    line = line.rstrip("\n\r")
                    lines.append(line)
                    on_line(line)
            except ValueError:
                pass

        t = threading.Thread(target=_pump, daemon=True)
        t.start()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            on_line(f"[超时] 命令执行超过 {timeout}s，已终止")
        t.join(timeout=5)
        try:
            proc.stdout.close()
        except Exception:
            pass
        return CmdResult(cmd, proc.returncode, "\n".join(lines), "")


@dataclass
class CancelableTask:
    """一个可被取消的异步任务句柄。"""

    name: str
    proc: Optional[subprocess.Popen] = None
    _stop: threading.Event = field(default_factory=threading.Event)

    def cancel(self):
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    @property
    def canceled(self) -> bool:
        return self._stop.is_set()
