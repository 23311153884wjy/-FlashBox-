"""设备、ADB、Fastboot 三个面板。"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import actions as A
from core.device import MODE_LABEL, kmi_of
from core.qrunner import JobThread, TaskThread

PARTITIONS = ["boot", "init_boot", "vendor_boot", "recovery", "vbmeta", "dtbo",
              "system", "vendor", "product", "super", "userdata", "cache"]


class DevicePanel(QWidget):
    """设备检测与连接状态。"""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        self.btn_scan = QPushButton("扫描设备")
        self.btn_scan.setProperty("primary", True)
        self.btn_scan.clicked.connect(self.scan)
        self.btn_detail = QPushButton("读取详细信息")
        self.btn_detail.clicked.connect(self.detail)
        self.btn_kill = QPushButton("重启 ADB 服务")
        self.btn_kill.clicked.connect(self.restart_adb)
        head.addWidget(self.btn_scan)
        head.addWidget(self.btn_detail)
        head.addWidget(self.btn_kill)
        head.addStretch()
        root.addLayout(head)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["序列号", "状态", "型号 / 代号", "安卓"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.setMinimumHeight(160)
        root.addWidget(self.table)

        info = QGroupBox("设备信息")
        il = QVBoxLayout(info)
        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(230)
        il.addWidget(self.info)
        root.addWidget(info)

        hint = QLabel("看不到设备？① 手机开启 USB 调试并点『允许』　② fastboot 模式需装对应驱动　"
                      "③ 显示 offline 换原装数据线　④ 9008 模式不会出现在 adb/fastboot 列表，请看『深度刷机』页")
        hint.setProperty("hint", True)
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch()

    def _on_select(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.ctx.devices):
            self.ctx.current = self.ctx.devices[row]
            self.info.setPlainText(self.ctx.current.summary())
            self.ctx.log(f"[选中] {self.ctx.current.serial}　{MODE_LABEL.get(self.ctx.current.mode, '')}")

    def scan(self):
        if not self.ctx.tools.adb and not self.ctx.tools.fastboot:
            QMessageBox.warning(self, "缺少工具", "请先在『工具箱』页配置 adb / fastboot。")
            return

        def job(emit):
            emit("[扫描] 正在检测连接...")
            devs = self.ctx.device_manager.scan()
            return devs

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(self._on_scan_done)
        self.thread.start()

    def _on_scan_done(self, devs):
        devs = devs or []
        self.ctx.devices = devs
        self.table.setRowCount(len(devs))
        for i, d in enumerate(devs):
            self.table.setItem(i, 0, QTableWidgetItem(d.serial))
            self.table.setItem(i, 1, QTableWidgetItem(MODE_LABEL.get(d.mode, d.mode)))
            self.table.setItem(i, 2, QTableWidgetItem(f"{d.model} / {d.codename}"))
            self.table.setItem(i, 3, QTableWidgetItem(d.android))
        if devs:
            self.table.selectRow(0)
            self.ctx.log(f"[扫描] 发现 {len(devs)} 台设备")
        else:
            self.info.setPlainText("")
            self.ctx.log("[扫描] 未发现设备")

    def detail(self):
        if not self.ctx.current:
            QMessageBox.information(self, "提示", "请先扫描并选中一台设备。")
            return

        def job(emit):
            emit("[信息] 正在读取属性...")
            self.ctx.device_manager.enrich(self.ctx.current)
            return self.ctx.current

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(self._on_detail_done)
        self.thread.start()

    def _on_detail_done(self, dev):
        if not dev:
            return
        text = dev.summary()
        kmi = kmi_of(dev.kernel)
        if kmi != "-":
            text += f"\nKMI：{kmi}　（选 GKI 镜像时照这个填）"
        text += "\n\n—— 全部属性 ——\n"
        for k in sorted(dev.props):
            if not k.startswith("_"):
                text += f"{k} = {dev.props[k]}\n"
        self.info.setPlainText(text)
        self.ctx.log("[信息] 读取完成")

    def restart_adb(self):
        if not self.ctx.tools.adb:
            return
        adb = self.ctx.tools.adb
        self.thread = TaskThread(self.ctx.runner, [adb, "kill-server"], 30)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(lambda _: self._after_kill(adb))
        self.thread.start()

    def _after_kill(self, adb):
        self.thread2 = TaskThread(self.ctx.runner, [adb, "start-server"], 30)
        self.thread2.line.connect(self.ctx.log)
        self.thread2.start()


class AdbPanel(QWidget):
    """ADB 常用操作。"""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        g1 = QGroupBox("重启控制")
        grid = QHBoxLayout(g1)
        for act in A.ADB_ACTIONS[:5]:
            b = QPushButton(act.label)
            if act.destructive:
                b.setProperty("danger", True)
            b.clicked.connect(lambda _=False, a=act: self.run(a))
            grid.addWidget(b)
        root.addWidget(g1)

        g2 = QGroupBox("常用操作")
        grid2 = QHBoxLayout(g2)
        for act in A.ADB_ACTIONS[5:7]:
            b = QPushButton(act.label)
            b.clicked.connect(lambda _=False, a=act: self.run(a))
            grid2.addWidget(b)
        self.btn_install = QPushButton("安装 APK（选文件）")
        self.btn_install.clicked.connect(self.install_apk)
        grid2.addWidget(self.btn_install)
        self.btn_push = QPushButton("推送文件到 /sdcard")
        self.btn_push.clicked.connect(self.push_file)
        grid2.addWidget(self.btn_push)
        root.addWidget(g2)

        g3 = QGroupBox("备份原厂镜像（救砖保命，强烈建议先做）")
        bl = QHBoxLayout(g3)
        self.part_combo = QComboBox()
        self.part_combo.addItems(["boot", "init_boot", "vendor_boot", "recovery", "dtbo"])
        bl.addWidget(QLabel("分区"))
        bl.addWidget(self.part_combo)
        bb = QPushButton("备份到电脑")
        bb.setProperty("primary", True)
        bb.clicked.connect(self.backup)
        bl.addWidget(bb)
        bl.addStretch()
        root.addWidget(g3)

        g4 = QGroupBox("自定义命令")
        cl = QHBoxLayout(g4)
        self.cmd_edit = QLineEdit()
        self.cmd_edit.setPlaceholderText("例如：shell getprop ro.build.fingerprint（不需要写 adb 前缀）")
        self.cmd_edit.returnPressed.connect(self.run_custom)
        cb = QPushButton("执行")
        cb.clicked.connect(self.run_custom)
        cl.addWidget(self.cmd_edit)
        cl.addWidget(cb)
        root.addWidget(g4)

        hint = QLabel("备份需要设备已有 root（su）。没有 root 时请从官方固件包里解包 boot.img 保存。")
        hint.setProperty("hint", True)
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch()

    def run(self, act: A.Action):
        if act.destructive and act.confirm:
            if QMessageBox.question(self, "二次确认", act.confirm) != QMessageBox.Yes:
                self.ctx.log("[取消] 用户取消了操作")
                return
        ok = self.ctx.actions.run_action(act, self.ctx.serial, self.ctx.log)
        if not ok:
            self.ctx.log(f"[失败] {act.label}")

    def install_apk(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 APK", "", "APK 文件 (*.apk)")
        if not path:
            return
        act = A.Action("install", "安装 APK", "adb", ["install", "-r", path])
        self.run(act)

    def push_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "所有文件 (*.*)")
        if not path:
            return
        act = A.Action("push", "推送文件", "adb", ["push", path, "/sdcard/"])
        self.run(act)

    def backup(self):
        if not self.ctx.current:
            QMessageBox.information(self, "提示", "请先选中设备。")
            return
        part = self.part_combo.currentText()
        out, _ = QFileDialog.getSaveFileName(self, "保存镜像", f"{part}.img", "镜像文件 (*.img)")
        if not out:
            return

        def job(emit):
            return self.ctx.actions.backup_partition(self.ctx.serial, part, out, emit)

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(lambda ok: self.ctx.log(f"[备份] {'成功：' + out if ok else '失败，请确认已 root'}"))
        self.thread.start()

    def run_custom(self):
        text = self.cmd_edit.text().strip()
        if not text:
            return
        import shlex
        try:
            args = shlex.split(text)
        except ValueError:
            args = text.split()
        act = A.Action("custom", "自定义", "adb", args)
        self.run(act)


class FastbootPanel(QWidget):
    """Fastboot 操作与镜像刷入。"""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        g1 = QGroupBox("状态与重启")
        h = QHBoxLayout(g1)
        for act in A.FASTBOOT_ACTIONS[:4]:
            b = QPushButton(act.label)
            b.clicked.connect(lambda _=False, a=act: self.run(a))
            h.addWidget(b)
        root.addWidget(g1)

        g2 = QGroupBox("刷入镜像")
        fl = QVBoxLayout(g2)
        row1 = QHBoxLayout()
        self.part_combo = QComboBox()
        self.part_combo.addItems(PARTITIONS)
        self.part_combo.setEditable(True)
        self.img_edit = QLineEdit()
        self.img_edit.setPlaceholderText("选择 .img 文件，留空则只生成命令")
        bb = QPushButton("浏览")
        bb.clicked.connect(self.pick_img)
        row1.addWidget(QLabel("分区"))
        row1.addWidget(self.part_combo)
        row1.addWidget(self.img_edit, 3)
        row1.addWidget(bb)
        fl.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_temp = QPushButton("临时引导验证（fastboot boot）")
        self.btn_temp.setProperty("primary", True)
        self.btn_temp.clicked.connect(self.temp_boot)
        self.btn_flash = QPushButton("永久刷入")
        self.btn_flash.setProperty("danger", True)
        self.btn_flash.clicked.connect(self.flash)
        self.chk_verity = QPushButton("刷 vbmeta 时自动去校验：开")
        self.chk_verity.setCheckable(True)
        self.chk_verity.setChecked(True)
        self.chk_verity.toggled.connect(self._on_verity)
        row2.addWidget(self.btn_temp)
        row2.addWidget(self.btn_flash)
        row2.addWidget(self.chk_verity)
        fl.addLayout(row2)
        root.addWidget(g2)

        g3 = QGroupBox("危险操作")
        dl = QHBoxLayout(g3)
        for act in A.FASTBOOT_ACTIONS[4:]:
            b = QPushButton(act.label)
            b.setProperty("danger", True)
            b.clicked.connect(lambda _=False, a=act: self.run(a))
            dl.addWidget(b)
        root.addWidget(g3)

        hint = QLabel("永久刷入前，先用『临时引导验证』跑一次：能进系统再刷，翻车只需重启。"
                      "刷 vbmeta 去校验可避免 avb 校验卡开机。")
        hint.setProperty("hint", True)
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch()

    def _on_verity(self, on):
        self.chk_verity.setText(f"刷 vbmeta 时自动去校验：{'开' if on else '关'}")

    def pick_img(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择镜像", "", "镜像文件 (*.img *.bin);;所有文件 (*.*)")
        if path:
            self.img_edit.setText(path)

    def _confirm_flash(self) -> bool:
        img = self.img_edit.text().strip()
        part = self.part_combo.currentText().strip()
        if not img or not os.path.isfile(img):
            QMessageBox.information(self, "提示", "请先选择一个镜像文件。")
            return False
        cmd = f"fastboot flash {part} {os.path.basename(img)}"
        return QMessageBox.question(
            self, "命令预览",
            f"即将执行：\n\n{cmd}\n\n刷错分区或镜像不匹配会无法开机。确定继续？"
        ) == QMessageBox.Yes

    def temp_boot(self):
        img = self.img_edit.text().strip()
        if not img or not os.path.isfile(img):
            QMessageBox.information(self, "提示", "请先选择一个镜像文件。")
            return

        def job(emit):
            return self.ctx.actions.temp_boot(self.ctx.serial, img, emit)

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(lambda ok: self.ctx.log(f"[临时引导] {'已下发，观察设备能否开机' if ok else '失败'}"))
        self.thread.start()

    def flash(self):
        if not self._confirm_flash():
            return
        img = self.img_edit.text().strip()
        part = self.part_combo.currentText().strip()

        def job(emit):
            return self.ctx.actions.flash_image(self.ctx.serial, part, img, emit,
                                                disable_verity=self.chk_verity.isChecked())

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(lambda ok: self.ctx.log(f"[刷入] {'成功' if ok else '失败'}"))
        self.thread.start()

    def run(self, act: A.Action):
        if act.destructive and act.confirm:
            if QMessageBox.question(self, "二次确认", act.confirm) != QMessageBox.Yes:
                self.ctx.log("[取消] 用户取消了操作")
                return
        self.ctx.actions.run_action(act, self.ctx.serial, self.ctx.log)
