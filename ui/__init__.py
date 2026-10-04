"""FlashBox 界面层。

界面模块统一用绝对导入（from core.xxx import ...），
这里负责把项目根塞进 sys.path，保证开发模式与 PyInstaller 打包后都能找到 core。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
