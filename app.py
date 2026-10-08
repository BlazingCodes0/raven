import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtGui import QIcon
from pathlib import Path

class Raven(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Raven — trading only")
        icon = Path.home() / "raven" / "assets" / "raven_neon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setMinimumSize(800, 600)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Raven — fresh start"))
        self.setCentralWidget(w)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    r = Raven()
    r.show()
    sys.exit(app.exec())
