"""应用上下文：各面板共享工具链、设备与日志通道。"""
from __future__ import annotations

from typing import Callable, List, Optional

from core.actions import Actions
from core.device import Device, DeviceManager
from core.executor import Runner
from core.toolchain import Toolchain


class AppContext:
    def __init__(self, log: Callable[[str], None]):
        self.log = log
        self.tools = Toolchain()
        self.runner = Runner(timeout=300)
        self.actions = Actions(self.tools.adb, self.tools.fastboot)
        self.devices: List[Device] = []
        self.current: Optional[Device] = None

    def sync_tools(self):
        """工具路径变化后，重建依赖它的对象。"""
        self.tools.refresh()
        self.actions = Actions(self.tools.adb, self.tools.fastboot)

    @property
    def device_manager(self) -> DeviceManager:
        return DeviceManager(self.tools.adb, self.tools.fastboot)

    @property
    def serial(self) -> Optional[str]:
        return self.current.serial if self.current else None

    def ready(self, tool: str) -> bool:
        return getattr(self.tools, tool, None) is not None
