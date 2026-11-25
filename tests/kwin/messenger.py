"""A program with a link: a click anywhere in its window opens it, as any Qt program would."""
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QPushButton

app = QApplication(["messenger"])
app.setDesktopFileName("messenger")
button = QPushButton("link")
button.resize(700, 500)
button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://example.com/x")))
button.show()
app.exec()
