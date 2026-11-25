"""The window with the tiles."""
import os
import sys
from collections.abc import Mapping

from .activation import request_token
from .model import Tile

ICON = "internet-web-browser"
ICON_SIZE = 96
TILE_WIDTH, TILE_HEIGHT = 180, 160
GUARD_MS = 300


def columns(count: int) -> int:
    return 2 if count <= 4 else 3 if count <= 9 else 4


def pick(tiles: list[Tile], label: str, last: str, strings: Mapping[str, str]) -> Tile | None:
    """Shows the window and returns the tile clicked, or None for "Cancel"."""
    from PyQt6.QtCore import QElapsedTimer, QSize, Qt
    from PyQt6.QtGui import QColor, QIcon, QPalette
    from PyQt6.QtWidgets import (
        QApplication, QButtonGroup, QDialog, QGridLayout, QLabel, QLayout, QToolButton)

    global app  # lives until the process ends: windows must not outlive QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setDesktopFileName("kde-browser-chooser")
    app.setWindowIcon(QIcon.fromTheme(ICON))

    picked: Tile | None = None
    shown = QElapsedTimer()

    class Window(QDialog):
        def paintEvent(self, event):
            if not shown.isValid():
                shown.start()
            super().paintEvent(event)

        def keyPressEvent(self, event):
            button = self.focusWidget()
            if button and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                button.click()
            else:
                super().keyPressEvent(event)

    def on_click(tile: Tile | None) -> None:
        nonlocal picked
        # The second click of a double click on the link must not choose a tile.
        if picked or not shown.isValid() or not shown.hasExpired(GUARD_MS):
            return
        picked = tile
        if tile and tile.command:
            request_token(window, window.accept)
        else:
            window.accept()

    def icon(name: str) -> QIcon:
        found = QIcon(name) if os.path.isabs(name) else QIcon.fromTheme(name)
        return QIcon.fromTheme(ICON) if found.isNull() else found

    def highlighted(palette: QPalette) -> QPalette:
        button, accent = QPalette.ColorRole.Button, QPalette.ColorRole.Highlight
        mix = [round(0.7 * b + 0.3 * a) for b, a in zip(palette.color(button).getRgb(), palette.color(accent).getRgb())]
        palette.setColor(button, QColor(*mix))
        return palette

    window = Window()
    window.setWindowTitle(strings["title"])
    grid = QGridLayout(window)
    grid.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
    group = QButtonGroup(window)  # makes the arrow keys follow the grid
    group.setExclusive(False)
    per_row = columns(len(tiles) + 1)

    for position, tile in enumerate([*tiles, None]):
        button = QToolButton()
        button.setText((tile.title if tile else strings["cancel"]).replace("&", "&&"))
        button.setIcon(icon(tile.icon if tile else "dialog-cancel"))
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setFixedSize(TILE_WIDTH, TILE_HEIGHT)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.clicked.connect(lambda _, tile=tile: on_click(tile))
        group.addButton(button)
        grid.addWidget(button, 1 + position // per_row, position % per_row)
        if tile and tile.id == last:
            button.setPalette(highlighted(button.palette()))
            button.setFocus()

    text = QLabel()
    text.setTextFormat(Qt.TextFormat.PlainText)
    width = per_row * TILE_WIDTH + (per_row - 1) * grid.horizontalSpacing()
    text.setText(text.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, width))
    grid.addWidget(text, 0, 0, 1, per_row)

    return picked if window.exec() else None
