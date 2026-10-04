"""Qt 线程包装：把耗时命令丢到后台，实时把输出刷到日志。"""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QThread, Signal

from .executor import CmdResult, Runner


class TaskThread(QThread):
    """后台执行单条命令，逐行发射输出。"""

    line = Signal(str)
    done = Signal(object)  # CmdResult

    def __init__(self, runner: Runner, cmd: List[str], timeout: int = 300, parent=None):
        super().__init__(parent)
        self.runner = runner
        self.cmd = cmd
        self.timeout = timeout
        self.result: Optional[CmdResult] = None

    def run(self):
        self.result = self.runner.run_stream(self.cmd, self.line.emit, self.timeout)
        self.done.emit(self.result)


class JobThread(QThread):
    """后台执行一个 Python 任务函数（用于非命令类操作，如扫描端口）。"""

    line = Signal(str)
    done = Signal(object)

    def __init__(self, func: Callable, parent=None):
        super().__init__(parent)
        self.func = func
        self.result = None

    def run(self):
        try:
            self.result = self.func(self.line.emit)
        except Exception as exc:  # 不让后台异常静默吞掉
            self.line.emit(f"[异常] {exc}")
            self.result = None
        self.done.emit(self.result)
