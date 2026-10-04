"""FlashBox 刷机工具箱 —— 程序入口。

Windows 打包后直接双击 FlashBox.exe 运行；开发模式执行 `python main.py`。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("缺少 PySide6，请先执行： pip install -r requirements.txt")
        return 1

    from PySide6.QtCore import Qt

    # 高分屏适配
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("FlashBox")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
