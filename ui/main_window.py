"""FlashBox 主窗口：左侧导航 + 右侧页面 + 底部日志。"""
from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.context import AppContext
from ui.panels_device import AdbPanel, DevicePanel, FastbootPanel
from ui.panels_root import EdlPanel, RootPanel, ToolsPanel
from ui.theme import DARK_QSS

DISCLAIMER = (
    "使用前请确认\n\n"
    "1. 本工具仅应用于你本人拥有、有权处置的设备。\n"
    "2. 刷机有风险：解锁 BL 会清空数据并影响保修（三星会永久熔断 Knox）。\n"
    "3. 动手前一定备份原厂 boot / init_boot，这是唯一的后悔药。\n"
    "4. Root 包、固件请只从各项目官方 Release 获取，警惕第三方镜像与网盘转载。\n\n"
    "继续即表示你已知悉以上风险。"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FlashBox 刷机工具箱  v1.0")
        self.resize(1080, 720)
        self.setStyleSheet(DARK_QSS)

        self.ctx = AppContext(self.log)
        self._build()
        self._boot_log()

    # ---------- 构建 ----------

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._build_nav())
        split.addWidget(self._build_pages())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([190, 890])
        root.addWidget(split, 1)

        root.addWidget(self._build_log())

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("就绪")

    def _build_nav(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 16, 12, 12)
        lay.setSpacing(6)

        title = QLabel("FlashBox")
        title.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        sub = QLabel("刷机工具箱 v1.0")
        sub.setProperty("hint", True)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(14)

        self.nav = QListWidget()
        self.nav_items = [
            ("设备", DevicePanel),
            ("ADB 工具", AdbPanel),
            ("Fastboot", FastbootPanel),
            ("Root 方案", RootPanel),
            ("深度刷机", EdlPanel),
            ("工具箱", ToolsPanel),
        ]
        for name, _cls in self.nav_items:
            self.nav.addItem(name)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._switch)
        lay.addWidget(self.nav, 1)

        btn = QPushButton("免责说明")
        btn.clicked.connect(self.show_disclaimer)
        lay.addWidget(btn)
        return box

    def _build_pages(self) -> QWidget:
        from PySide6.QtWidgets import QStackedWidget

        self.stack = QStackedWidget()
        self.pages = []
        for _name, cls in self.nav_items:
            p = cls(self.ctx)
            self.stack.addWidget(p)
            self.pages.append(p)
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        return wrap

    def _build_log(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 6, 12, 10)
        lay.setSpacing(4)

        head = QHBoxLayout()
        lb = QLabel("运行日志")
        lb.setProperty("hint", True)
        self.log_view = QTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(180)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setFixedWidth(70)
        self.btn_clear.clicked.connect(self.log_view.clear)
        self.btn_copy = QPushButton("复制全部")
        self.btn_copy.setFixedWidth(90)
        self.btn_copy.clicked.connect(self._copy_log)
        head.addWidget(lb)
        head.addStretch()
        head.addWidget(self.btn_copy)
        head.addWidget(self.btn_clear)

        lay.addLayout(head)
        lay.addWidget(self.log_view)
        return box

    def _switch(self, row: int):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
            self.status.showMessage(self.nav_items[row][0])

    # ---------- 日志 ----------

    def log(self, text: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {text}")
        self.log_view.ensureCursorVisible()

    def _copy_log(self):
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.log_view.toPlainText())
        self.status.showMessage("日志已复制到剪贴板", 3000)

    def _boot_log(self):
        self.log("FlashBox 已启动")
        st = self.ctx.tools.status()
        if st["ready"]:
            self.log(f"adb / fastboot 就绪　{st['adb_version']}")
        else:
            self.log("未检测到 adb / fastboot，请到『工具箱』页下载或指定路径")
            self._switch(5)
            self.nav.setCurrentRow(5)

    def show_disclaimer(self):
        QMessageBox.information(self, "免责说明", DISCLAIMER)
