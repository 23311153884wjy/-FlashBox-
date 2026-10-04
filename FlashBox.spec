# -*- mode: python ; coding: utf-8 -*-
"""FlashBox 打包配置（onedir 模式：启动快、便于随包携带 platform-tools）。"""
import os

block_cipher = None

project_root = os.path.abspath(SPECPATH)  # noqa: F821

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

# 随包携带的 platform-tools（存在才打包）
datas = []
pt_dir = os.path.join(project_root, "tools", "platform-tools")
if os.path.isdir(pt_dir):
    datas.append((pt_dir, os.path.join("tools", "platform-tools")))

a = Analysis(  # noqa: F821
    ["main.py"],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "tkinter",
        "numpy",
        "matplotlib",
        "PIL",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FlashBox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI 程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, "assets", "icon.ico")
    if os.path.isfile(os.path.join(project_root, "assets", "icon.ico"))
    else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FlashBox",
)
