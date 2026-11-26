"""A running browser: on a token in the FIFO it asks to be activated and tells whether that worked."""
import os
import sys

from PyQt6.QtCore import QSocketNotifier, QTimer
from PyQt6.QtWidgets import QApplication, QLabel

fifo, result = sys.argv[1:]
app = QApplication(["browser"])
app.setDesktopFileName("fakebrowser")
window = QLabel("browser")
window.resize(900, 650)
window.show()
fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)


def report():
    with open(result, "w") as file:
        file.write(f"{window.isActiveWindow()}\n")


def link_opened():
    os.environ["XDG_ACTIVATION_TOKEN"] = os.read(fd, 4096).decode().strip()
    window.windowHandle().requestActivate()
    QTimer.singleShot(800, report)


notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read)
notifier.activated.connect(lambda *_: link_opened())
app.exec()
