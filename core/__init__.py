"""FlashBox 核心层：不依赖 Qt 的纯逻辑（命令执行、设备解析、方案定义）。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
