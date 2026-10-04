"""全局样式：深色科技风，贴近主流刷机工具的观感。"""

DARK_QSS = """
QWidget { background:#12151c; color:#dfe4ee; font-family:"Microsoft YaHei UI","Microsoft YaHei"; font-size:13px; }
QMainWindow, QDialog { background:#12151c; }

QListWidget { background:#171b25; border:none; border-radius:10px; padding:8px 4px; }
QListWidget::item { padding:11px 14px; border-radius:8px; margin:2px 6px; color:#a8b2c4; }
QListWidget::item:hover { background:#1e2432; color:#e6ebf5; }
QListWidget::item:selected { background:#2563eb; color:#ffffff; font-weight:600; }

QPushButton {
    background:#222836; border:1px solid #2f3850; border-radius:8px;
    padding:8px 14px; color:#dfe4ee;
}
QPushButton:hover { background:#2b3346; border-color:#3f4c6b; }
QPushButton:pressed { background:#1b2030; }
QPushButton:disabled { background:#191d27; color:#5b6478; border-color:#232838; }
QPushButton[primary="true"] { background:#2563eb; border-color:#2563eb; color:#ffffff; font-weight:600; }
QPushButton[primary="true"]:hover { background:#3b76ef; }
QPushButton[danger="true"] { background:#3a1d24; border-color:#7f2b39; color:#ff9aa8; }
QPushButton[danger="true"]:hover { background:#4a232c; }

QGroupBox {
    border:1px solid #262c3c; border-radius:10px; margin-top:16px;
    padding:14px 12px 12px 12px; font-weight:600; color:#9fb0cc;
}
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 6px; color:#7fa4e8; }

QLineEdit, QComboBox, QTextEdit, QSpinBox {
    background:#1a1f2b; border:1px solid #2b3346; border-radius:8px;
    padding:7px 10px; color:#e6ebf5; selection-background-color:#2563eb;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color:#2563eb; }
QComboBox::drop-down { border:none; width:22px; }
QComboBox QAbstractItemView { background:#1a1f2b; border:1px solid #2b3346; selection-background-color:#2563eb; }

QTableWidget { background:#161a24; border:1px solid #262c3c; border-radius:8px; gridline-color:#232a38; }
QHeaderView::section { background:#1c2230; color:#9fb0cc; border:none; padding:7px; font-weight:600; }
QTableWidget::item { padding:5px 8px; }

QLabel[hint="true"] { color:#7c8699; font-size:12px; }
QLabel[ok="true"] { color:#4ade80; }
QLabel[warn="true"] { color:#fbbf24; }
QLabel[err="true"] { color:#f87171; }

QTextEdit#log { background:#0d1017; border:1px solid #202634; border-radius:8px;
    font-family:"Cascadia Mono","Consolas","Microsoft YaHei"; font-size:12px; color:#9fe6b8; }

QStatusBar { background:#171b25; color:#7c8699; }
QScrollBar:vertical { background:#141821; width:10px; margin:0; border-radius:5px; }
QScrollBar::handle:vertical { background:#2c3446; border-radius:5px; min-height:28px; }
QScrollBar::handle:vertical:hover { background:#3a4459; }
QScrollBar:horizontal { height:0; }
"""
