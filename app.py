import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

BLACK = "#000000"
PANEL = "#0a0a0a"
EDGE = "#1e1e1e"
TEXT = "#d4d4d4"
MUTED = "#6b6b6b"
NEON = "#00e5ff"
NEON2 = "#a855f7"

STYLE = f"""
QMainWindow, QWidget#root {{
    background: {BLACK};
    color: {TEXT};
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel#title {{
    color: {NEON};
    font-size: 22px;
    font-weight: bold;
    letter-spacing: 6px;
}}
QLabel#sub {{
    color: {MUTED};
    font-size: 11px;
    letter-spacing: 2px;
}}
QLabel#accent {{
    color: {NEON};
}}
QFrame#header {{
    background: {BLACK};
    border-bottom: 1px solid {EDGE};
}}
QTabWidget::pane {{
    border: 1px solid {EDGE};
    background: {PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background: {BLACK};
    color: {MUTED};
    padding: 10px 22px;
    margin-right: 1px;
    border: 1px solid {EDGE};
    border-bottom: none;
    font-size: 12px;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QTabBar::tab:selected {{
    background: {PANEL};
    color: {NEON};
    border-top: 2px solid {NEON};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
    border-color: {NEON2};
}}
QPlainTextEdit {{
    background: {BLACK};
    color: {TEXT};
    border: 1px solid {EDGE};
    font-family: monospace;
    font-size: 13px;
    padding: 8px;
    selection-background-color: {NEON2};
}}
QLabel#placeholder {{
    color: {MUTED};
    font-size: 14px;
}}
QStatusBar {{
    background: {BLACK};
    color: {MUTED};
    border-top: 1px solid {EDGE};
    font-size: 11px;
}}
"""


class Panel(QFrame):
    """A single tab body: black panel with a heading and a body layout."""

    def __init__(self, title, subtitle=""):
        super().__init__()
        self.setObjectName("panel")
        self.setStyleSheet(
            f"QFrame#panel {{ background: {PANEL}; border: none; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(2)
        h = QLabel(title)
        h.setObjectName("accent")
        h.setStyleSheet(f"color: {NEON}; font-size: 16px; font-weight: bold; letter-spacing: 3px;")
        head.addWidget(h)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("sub")
            head.addWidget(s)
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

    def add(self, widget):
        self.body.addWidget(widget)
        return widget


def placeholder(text):
    lbl = QLabel(text)
    lbl.setObjectName("placeholder")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


class Raven(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Raven")
        icon = Path(__file__).parent / "assets" / "raven_neon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1100, 720)
        self.setMinimumSize(760, 520)

        root = QWidget()
        root.setObjectName("root")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 16)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        t = QLabel("RAVEN")
        t.setObjectName("title")
        title_box.addWidget(t)
        sub = QLabel("SECURITY LAB // LOCAL AUTHORIZED TESTING ONLY")
        sub.setObjectName("sub")
        title_box.addWidget(sub)
        hl.addLayout(title_box)
        hl.addStretch(1)
        mode = QLabel("OFFLINE")
        mode.setStyleSheet(
            f"color: {NEON}; border: 1px solid {NEON}; padding: 4px 12px; "
            f"font-size: 11px; letter-spacing: 2px;"
        )
        hl.addWidget(mode)
        lay.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.build_tabs()
        lay.addWidget(self.tabs, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready — only run against devices you own or have permission to test.")

    def build_tabs(self):
        # Dashboard
        dash = Panel("DASHBOARD", "system overview")
        dash.add(placeholder("No data yet.\nModules will report here."))
        self.tabs.addTab(dash, "Dashboard")

        # Recon
        recon = Panel("RECON", "enumerate and fingerprint the target")
        recon.add(placeholder("Recon tools land here."))
        self.tabs.addTab(recon, "Recon")

        # Scan
        scan = Panel("SCAN", "port / service discovery")
        scan.add(placeholder("Scanner output lands here."))
        self.tabs.addTab(scan, "Scan")

        # Modules
        mods = Panel("MODULES", "pluggable tools")
        mods.add(placeholder("Modules land here."))
        self.tabs.addTab(mods, "Modules")

        # Logs
        logs = Panel("LOGS", "raw output")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("stdout / stderr appears here")
        logs.add(self.log_view)
        self.tabs.addTab(logs, "Logs")

        # Settings
        settings = Panel("SETTINGS", "configuration")
        settings.add(placeholder("Settings land here."))
        self.tabs.addTab(settings, "Settings")

    def log(self, text):
        self.log_view.appendPlainText(text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("monospace", 10))
    raven = Raven()
    raven.show()
    sys.exit(app.exec())
