"""Root 方案、深度刷机、工具箱三个面板。"""
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

from core import edl as E
from core import rootsol as RS
from core.device import kmi_of
from core.qrunner import JobThread
from core.rootops import RootOps, patch_plan


class RootPanel(QWidget):
    """内核级 Root：KSU / KSUN / SukiSU-Ultra / APatch / FolkPatch。"""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.sol = RS.get("ksu")
        self._mods: list = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # ---- 方案选择 ----
        g0 = QGroupBox("① 选择 Root 方案")
        h0 = QHBoxLayout(g0)
        self.sol_combo = QComboBox()
        for s in RS.all_solutions():
            self.sol_combo.addItem(f"{s.name}", s.key)
        self.sol_combo.currentIndexChanged.connect(self._on_sol)
        h0.addWidget(QLabel("方案"))
        h0.addWidget(self.sol_combo, 2)

        self.mode_combo = QComboBox()
        self.mode_combo.currentIndexChanged.connect(self._refresh_plan)
        h0.addWidget(QLabel("模式"))
        h0.addWidget(self.mode_combo, 1)
        root.addWidget(g0)

        self.sol_info = QTextEdit()
        self.sol_info.setReadOnly(True)
        self.sol_info.setMaximumHeight(140)
        root.addWidget(self.sol_info)

        # ---- 设备状态 ----
        g1 = QGroupBox("② 当前设备（影响刷入分区的判定）")
        v1 = QVBoxLayout(g1)
        h1 = QHBoxLayout()
        self.dev_label = QLabel("未检测")
        self.dev_label.setProperty("hint", True)
        b1 = QPushButton("读取设备状态")
        b1.clicked.connect(self.detect)
        h1.addWidget(self.dev_label, 1)
        h1.addWidget(b1)
        v1.addLayout(h1)
        self.override = QComboBox()
        self.override.addItems(["自动判定", "强制 boot", "强制 init_boot"])
        h1.addWidget(QLabel("分区"))
        h1.addWidget(self.override)
        self.override.currentIndexChanged.connect(self._refresh_plan)
        root.addWidget(g1)

        # ---- 流程 ----
        g2 = QGroupBox("③ 修补与刷入流程")
        v2 = QVBoxLayout(g2)
        h2 = QHBoxLayout()
        self.img_edit = QLineEdit()
        self.img_edit.setPlaceholderText("修补后的镜像路径（GKI 模式为官方 GKI boot.img）")
        bb = QPushButton("浏览")
        bb.clicked.connect(self.pick_img)
        h2.addWidget(self.img_edit, 3)
        h2.addWidget(bb)
        v2.addLayout(h2)
        self.plan_view = QTextEdit()
        self.plan_view.setReadOnly(True)
        self.plan_view.setMinimumHeight(190)
        v2.addWidget(self.plan_view)
        root.addWidget(g2)

        # ---- 模块 ----
        g3 = QGroupBox("④ 模块管理（需设备已 root）")
        v3 = QVBoxLayout(g3)
        self.mod_table = QTableWidget(0, 3)
        self.mod_table.setHorizontalHeaderLabels(["模块 ID", "状态", "操作"])
        self.mod_table.horizontalHeader().setStretchLastSection(True)
        self.mod_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mod_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mod_table.setMinimumHeight(150)
        v3.addWidget(self.mod_table)
        h3 = QHBoxLayout()
        b_refresh = QPushButton("刷新模块列表")
        b_refresh.clicked.connect(self.list_modules)
        b_inst = QPushButton("安装模块 ZIP")
        b_inst.setProperty("primary", True)
        b_inst.clicked.connect(self.install_module)
        h3.addWidget(b_refresh)
        h3.addWidget(b_inst)
        if self.sol.kpm:
            b_kpm = QPushButton("加载 KPM")
            b_kpm.clicked.connect(self.load_kpm)
            h3.addWidget(b_kpm)
        h3.addStretch()
        v3.addLayout(h3)
        root.addWidget(g3)

        self.warn = QLabel("")
        self.warn.setProperty("warn", True)
        self.warn.setWordWrap(True)
        root.addWidget(self.warn)
        root.addStretch()

        self._on_sol()

    # ---------- 事件 ----------

    def _on_sol(self):
        self.sol = RS.get(self.sol_combo.currentData())
        self.sol_info.setPlainText(self.sol.describe())
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for m in self.sol.modes:
            label = {"LKM": "LKM（改 ramdisk，风险最低）",
                     "GKI": "GKI（整体换内核）",
                     "boot_patch": "修补 boot.img"}.get(m, m)
            self.mode_combo.addItem(label, m)
        self.mode_combo.blockSignals(False)
        self.warn.setText(self.sol.risk or "")
        self._refresh_plan()

    def _refresh_plan(self):
        mode = self.mode_combo.currentData() or (self.sol.modes[0] if self.sol.modes else "LKM")
        dev = self.ctx.current
        android = dev.android if dev else ""
        has_ib = dev.has_init_boot if dev else False
        part = RS.choose_patch_partition(self.sol, mode, has_ib, android)
        if self.override.currentIndex() == 1:
            part = "boot"
        elif self.override.currentIndex() == 2:
            part = "init_boot"
        steps = patch_plan(self.sol, mode, has_ib, android, self.img_edit.text().strip(), self.ctx.serial)
        text = f"目标分区：{part}\n\n"
        for s in steps:
            text += f"{s['title']}\n　{s['cmd']}\n\n"
        self.plan_view.setPlainText(text)

    def pick_img(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择镜像", "", "镜像文件 (*.img);;所有文件 (*.*)")
        if path:
            self.img_edit.setText(path)
            self._refresh_plan()

    def detect(self):
        if not self.ctx.current:
            QMessageBox.information(self, "提示", "请先在『设备』页扫描并选中设备。")
            return

        def job(emit):
            emit("[Root] 读取设备状态...")
            self.ctx.device_manager.enrich(self.ctx.current)
            ops = RootOps(self.ctx.tools.adb, self.ctx.serial)
            impl = ops.detect_root_impl()
            ver = ops.su_version()
            return impl, ver

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(self._on_detect)
        self.thread.start()

    def _on_detect(self, res):
        if not res:
            return
        impl, ver = res
        dev = self.ctx.current
        kmi = kmi_of(dev.kernel) if dev else "-"
        state = "已 Root" if impl not in ("none",) else "未 Root"
        self.dev_label.setText(
            f"{dev.model}　安卓 {dev.android}　内核 {dev.kernel}　KMI {kmi}　→ {state}（{impl} / {ver}）"
        )
        self.dev_label.setProperty("ok", impl != "none")
        self.dev_label.setProperty("err", impl == "none")
        self.dev_label.style().polish(self.dev_label)
        if impl == "none":
            self.ctx.log("[Root] 当前无 root，请先按上方流程刷入")
        self._refresh_plan()

    # ---------- 模块 ----------

    def _ops(self):
        return RootOps(self.ctx.tools.adb, self.ctx.serial)

    def list_modules(self):
        def job(emit):
            emit("[模块] 读取列表...")
            return self._ops().list_modules(self.sol)

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(self._on_modules)
        self.thread.start()

    def _on_modules(self, mods):
        mods = mods or []
        self.mod_table.setRowCount(len(mods))
        self._mods = mods
        for i, m in enumerate(mods):
            state = "待移除" if m["removed"] else ("启用" if m["enabled"] else "已禁用")
            self.mod_table.setItem(i, 0, QTableWidgetItem(m["id"]))
            st = QTableWidgetItem(state)
            self.mod_table.setItem(i, 1, st)
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(2, 2, 2, 2)
            b1 = QPushButton("禁用" if m["enabled"] else "启用")
            b1.clicked.connect(lambda _=False, i=i: self.toggle(i))
            b2 = QPushButton("移除")
            b2.setProperty("danger", True)
            b2.clicked.connect(lambda _=False, i=i: self.remove(i))
            h.addWidget(b1)
            h.addWidget(b2)
            self.mod_table.setCellWidget(i, 2, box)
        self.ctx.log(f"[模块] 共 {len(mods)} 个")

    def toggle(self, i):
        m = self._mods[i]
        op = "disable" if m["enabled"] else "enable"
        ok, out = self._ops().set_module_state(self.sol, m["id"], op)
        self.ctx.log(f"[模块] {m['id']} {op} → {'成功，重启生效' if ok else '失败：' + out}")
        if ok:
            self.list_modules()

    def remove(self, i):
        m = self._mods[i]
        if QMessageBox.question(self, "确认", f"移除模块 {m['id']}？重启后生效，部分模块移除会导致功能异常。") != QMessageBox.Yes:
            return
        ok, out = self._ops().set_module_state(self.sol, m["id"], "remove")
        self.ctx.log(f"[模块] {m['id']} remove → {'成功' if ok else '失败：' + out}")
        if ok:
            self.list_modules()

    def install_module(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择模块 ZIP", "", "模块包 (*.zip)")
        if not path:
            return

        def job(emit):
            return self._ops().install_module(self.sol, path, emit)

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(lambda ok: self.ctx.log(f"[模块] 安装{'成功' if ok else '失败'}"))
        self.thread.start()

    def load_kpm(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 KPM", "", "内核模块 (*.kpm);;所有文件 (*.*)")
        if not path:
            return

        def job(emit):
            return self._ops().load_kpm(self.sol, path, emit)

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(lambda ok: self.ctx.log(f"[KPM] 加载{'成功' if ok else '失败'}"))
        self.thread.start()


class EdlPanel(QWidget):
    """9008 / MTK / 展锐 深度刷机识别与引导。"""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        g1 = QGroupBox("① 扫描底层下载端口")
        v1 = QVBoxLayout(g1)
        h1 = QHBoxLayout()
        b = QPushButton("扫描 COM / 串口")
        b.setProperty("primary", True)
        b.clicked.connect(self.scan)
        h1.addWidget(b)
        h1.addStretch()
        v1.addLayout(h1)
        self.port_table = QTableWidget(0, 3)
        self.port_table.setHorizontalHeaderLabels(["端口", "平台判定", "设备描述"])
        self.port_table.horizontalHeader().setStretchLastSection(True)
        self.port_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.port_table.setMinimumHeight(140)
        v1.addWidget(self.port_table)
        root.addWidget(g1)

        g2 = QGroupBox("② 引导进入 9008 / 下载模式")
        v2 = QVBoxLayout(g2)
        h2 = QHBoxLayout()
        self.cmd_combo = QComboBox()
        for i, item in enumerate(E.edl_entry_commands()):
            self.cmd_combo.addItem(f"{item['label']}　[风险：{item['risk']}]", i)
        be = QPushButton("执行")
        be.setProperty("danger", True)
        be.clicked.connect(self.exec_cmd)
        h2.addWidget(self.cmd_combo, 3)
        h2.addWidget(be)
        v2.addLayout(h2)
        root.addWidget(g2)

        g3 = QGroupBox("③ 对应工具指引")
        v3 = QVBoxLayout(g3)
        self.guide = QTextEdit()
        self.guide.setReadOnly(True)
        self.guide.setMinimumHeight(170)
        v3.addWidget(self.guide)
        root.addWidget(g3)

        hint = QLabel("本页只做识别与引导，不代跑 QFIL / SP Flash Tool 等第三方工具。"
                      "高通需要 firehose 编程器文件、联发科需要 scatter + DA、展锐需要 pac 包，请自备对应机型的合法固件。")
        hint.setProperty("hint", True)
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch()

    def scan(self):
        def job(emit):
            emit("[深度] 扫描端口...")
            return E.scan_ports()

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(self._on_ports)
        self.thread.start()

    def _on_ports(self, ports):
        ports = ports or []
        self.port_table.setRowCount(len(ports))
        guides = []
        for i, p in enumerate(ports):
            self.port_table.setItem(i, 0, QTableWidgetItem(p.device))
            label = next((v[0] for k, v in E.PORT_SIGNATURES.items() if k.lower() in p.description.lower()),
                         p.description)
            self.port_table.setItem(i, 1, QTableWidgetItem(label))
            self.port_table.setItem(i, 2, QTableWidgetItem(p.description))
            if p.platform not in guides:
                guides.append(p.platform)
        if ports:
            text = ""
            for g in guides:
                text += f"【{g}】\n" + "\n".join(f"　· {t}" for t in E.guide_for(g)) + "\n\n"
            self.guide.setPlainText(text or "未识别到已知平台")
            self.ctx.log(f"[深度] 发现 {len(ports)} 个端口")
        else:
            self.guide.setPlainText("未扫描到端口。设备处于 9008 时屏幕全黑且无任何显示，属正常现象。")
            self.ctx.log("[深度] 无端口")

    def exec_cmd(self):
        items = E.edl_entry_commands()
        item = items[self.cmd_combo.currentData()]
        if item["tool"] != "manual":
            if QMessageBox.question(self, "确认", f"即将执行：\n{item['cmd']}\n\n确定继续？") != QMessageBox.Yes:
                return
        E.run_edl_command(self.ctx.tools.adb, self.ctx.tools.fastboot, item, self.ctx.log)


class ToolsPanel(QWidget):
    """adb / fastboot 工具链配置。"""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        g1 = QGroupBox("工具状态")
        v1 = QVBoxLayout(g1)
        self.status = QTextEdit()
        self.status.setReadOnly(True)
        self.status.setMaximumHeight(120)
        v1.addWidget(self.status)
        h1 = QHBoxLayout()
        b1 = QPushButton("重新检测")
        b1.setProperty("primary", True)
        b1.clicked.connect(lambda: (self.ctx.sync_tools(), self.refresh()))
        h1.addWidget(b1)
        h1.addStretch()
        v1.addLayout(h1)
        root.addWidget(g1)

        g2 = QGroupBox("自动获取官方 platform-tools")
        v2 = QVBoxLayout(g2)
        h2 = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("解压目录，留空则下载到程序目录下 tools/")
        bd = QPushButton("浏览")
        bd.clicked.connect(self.pick_dir)
        bdl = QPushButton("下载官方 platform-tools")
        bdl.setProperty("primary", True)
        bdl.clicked.connect(self.download)
        h2.addWidget(self.dir_edit, 3)
        h2.addWidget(bd)
        h2.addWidget(bdl)
        v2.addLayout(h2)
        root.addWidget(g2)

        g3 = QGroupBox("说明")
        v3 = QVBoxLayout(g3)
        t = QTextEdit()
        t.setReadOnly(True)
        t.setPlainText(
            "· 建议把 Google 官方 platform-tools 解压到程序目录下的 tools/platform-tools，\n"
            "　这样 exe 拷到哪台电脑都能直接用，不依赖系统 PATH。\n\n"
            "· 官方地址（滚动更新到最新版）：\n"
            "　https://dl.google.com/android/repository/platform-tools-latest-windows.zip\n\n"
            "· 手机在 fastboot 模式下需要单独装驱动（与开机状态不是同一个驱动）。\n"
            "　ADB 能识别 ≠ fastboot 能识别，这是最常见的「连不上」原因。\n\n"
            "· 本工具不会替你下载任何 Root 包 / 固件，各方案镜像请只从官方 Release 获取。"
        )
        v3.addWidget(t)
        root.addWidget(g3)
        root.addStretch()

    def refresh(self):
        st = self.ctx.tools.status()
        ok = st["ready"]
        self.status.setPlainText(
            f"adb      ：{st['adb']}\n"
            f"        　版本 {st['adb_version']}\n"
            f"fastboot ：{st['fastboot']}\n"
            f"        　版本 {st['fastboot_version']}\n"
            f"状态     ：{'就绪' if ok else '缺失，请下载或手动指定'}"
        )

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择解压目录")
        if d:
            self.dir_edit.setText(d)

    def download(self):
        from core.toolchain import app_dir, download_platform_tools

        dest = self.dir_edit.text().strip() or os.path.join(app_dir(), "tools")

        def job(emit):
            emit(f"[下载] 目标目录：{dest}")
            return download_platform_tools(dest, lambda p: emit(f"[下载] {p}%"))

        self.thread = JobThread(job)
        self.thread.line.connect(self.ctx.log)
        self.thread.done.connect(self._after_download)
        self.thread.start()

    def _after_download(self, path):
        if path:
            self.ctx.log(f"[下载] 完成：{path}")
            self.ctx.sync_tools()
            self.refresh()
        else:
            self.ctx.log("[下载] 失败，请检查网络或手动下载解压到 tools/platform-tools")
