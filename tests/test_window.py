import os
import sys

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QIcon, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QToolButton

from kde_browser_chooser import activation, window
from kde_browser_chooser.model import Tile

COPY = Tile("copy", "Copy link", "edit-copy", None)
CHROME = Tile("chrome", "Google Chrome", "google-chrome", ("chrome", "%U"))
FIREFOX = Tile("firefox", "Firefox", "firefox", ("firefox", "%u"))
YANDEX = Tile("yandex", "Yandex", "yandex-browser", ("yandex", "%U"))
OPERA = Tile("opera", "Opera", "opera", ("opera", "%U"))
TILES = [COPY, CHROME, FIREFOX, YANDEX, OPERA]
STRINGS = {"title": "Open link", "cancel": "Cancel"}
LEFT = Qt.MouseButton.LeftButton
app = QApplication.instance() or QApplication(["test"])


def visible_dialog():
    return next((w for w in app.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()), None)


class FirstPaint(QObject):
    """Starts the given timers at the first paint of a dialog."""

    def __init__(self, timers):
        super().__init__()
        self.timers = timers

    def eventFilter(self, watched, event):
        if self.timers and event.type() == QEvent.Type.Paint and isinstance(watched, QDialog):
            for timer, delay in self.timers:
                timer.start(delay)
            self.timers = []
        return False


def drive(action, tiles=TILES, label="https://e.com/", last="copy", wait=None, strings=STRINGS, counter=""):
    """Shows the window, calls action(dialog) wait ms after its first paint, returns the choice."""
    failures = []

    def act():
        try:
            action(visible_dialog())
        except BaseException as error:  # an exception in a slot would abort the process
            failures.append(error)

    def give_up():
        if visible_dialog():
            visible_dialog().reject()

    wait = window.GUARD_MS + 100 if wait is None else wait
    timers = []
    for slot, delay in ((act, wait), (give_up, wait + 1000)):
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        timer.timeout.connect(slot)
        timers.append((timer, delay))
    paint = FirstPaint(list(timers))
    app.installEventFilter(paint)
    try:
        result = window.pick(tiles, label, counter, last, strings)
    finally:
        app.removeEventFilter(paint)
        for timer, _ in timers:
            timer.stop()
    if failures:
        raise failures[0]
    return result


def buttons(dialog):
    return sorted(dialog.findChildren(QToolButton), key=lambda b: (b.y(), b.x()))


def button(dialog, title):
    return next(b for b in buttons(dialog) if b.text() == title)


def click(dialog, title, pos=QPoint(4, 4)):
    QTest.mouseClick(button(dialog, title), LEFT, pos=pos)


@pytest.mark.parametrize("count, want", [(1, 2), (2, 2), (4, 2), (5, 3), (6, 3), (9, 3), (10, 4), (16, 4)])
def test_columns(count, want):
    assert window.columns(count) == want


def test_grid():
    seen = {}

    def look(dialog):
        seen["buttons"] = [(b.text(), b.x(), b.y(), b.width(), b.height(), b.iconSize()) for b in buttons(dialog)]
        seen["title"] = dialog.windowTitle()

    drive(look)
    titles, xs, ys, widths, heights, icons = zip(*seen["buttons"])
    assert list(titles) == ["Copy link", "Google Chrome", "Firefox", "Yandex", "Opera", "Cancel"]
    assert len(set(xs)) == 3 and len(set(ys)) == 2
    assert set(widths) == {180} and set(heights) == {160}
    assert set((i.width(), i.height()) for i in icons) == {(96, 96)}
    assert seen["title"] == "Open link"


@pytest.mark.parametrize("tiles", [[], [COPY], TILES[:4], [*TILES, *(
    Tile(str(i), str(i), "", ("x", "%u")) for i in range(5))]])
def test_cancel_is_always_last(tiles):
    seen = []
    drive(lambda d: seen.extend(b.text() for b in buttons(d)), tiles=tiles)
    assert seen[-1] == "Cancel" and len(seen) == len(tiles) + 1


@pytest.mark.parametrize("tile", TILES, ids=lambda tile: tile.id)
def test_one_click(tile):
    assert drive(lambda d: click(d, tile.title)) == tile


def test_click_anywhere_on_the_tile():
    def far_corner(dialog):
        b = button(dialog, "Opera")
        click(dialog, "Opera", QPoint(b.width() - 4, b.height() - 4))

    assert drive(far_corner) == OPERA


def test_cancel_tile():
    assert drive(lambda d: click(d, "Cancel")) is None


def test_escape():
    assert drive(lambda d: QTest.keyClick(d, Qt.Key.Key_Escape)) is None


def test_close():
    assert drive(lambda d: d.close()) is None


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_opens_the_last_choice(key):
    def press(dialog):
        assert dialog.focusWidget().text() == "Yandex"
        QTest.keyClick(dialog.focusWidget(), key)

    assert drive(press, last="yandex") == YANDEX


def test_arrows_follow_the_grid():
    seen = []

    def walk(dialog):
        for key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Up):
            QTest.keyClick(dialog.focusWidget(), key)
            seen.append(dialog.focusWidget().text())

    drive(walk)
    assert seen == ["Google Chrome", "Opera", "Yandex", "Copy link"]


@pytest.mark.parametrize("wait, want", [(30, None), (200, None), (345, CHROME)])
def test_guard_is_300_ms(wait, want):
    assert drive(lambda d: click(d, "Google Chrome"), wait=wait) == want


@pytest.mark.parametrize("wait, want", [(200, None), (345, CHROME)])
def test_guard_counts_the_press(wait, want):
    """The second click of a double click on the link can be pressed within the guard and released after it."""

    def press_then_release(dialog):
        target = button(dialog, "Google Chrome")
        QTest.mousePress(target, LEFT, pos=QPoint(4, 4))
        QTest.qWait(200)
        QTest.mouseRelease(target, LEFT, pos=QPoint(4, 4))

    assert drive(press_then_release, wait=wait) == want


def test_early_escape_works():
    seen = []

    def escape(dialog):
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        seen.append(dialog.isVisible())

    drive(escape, wait=30)
    assert seen == [False]


def look_at(label, counter=""):
    seen = {}

    def look(dialog):
        text = dialog.findChild(QLabel)
        seen.update(size=QSize(dialog.size()), text=text.text(), format=text.textFormat())

    drive(look, label=label, counter=counter)
    return seen


def test_long_link():
    short, long = look_at("https://e.com/"), look_at("https://e.com/" + "x" * 5000)
    assert long["size"] == short["size"]
    assert long["text"].startswith("https://e.com/xxx") and long["text"].endswith("…")


def test_long_link_keeps_the_counter():
    short, long = look_at("https://e.com/", "(+1)"), look_at("https://e.com/" + "x" * 5000, "(+1)")
    assert short["text"] == "https://e.com/ (+1)"
    assert long["size"] == short["size"]
    assert long["text"].startswith("https://e.com/xxx") and long["text"].endswith("… (+1)")


def test_link_is_literal():
    link = "https://e.com/?a=1&b=<b>2</b>"
    seen = look_at(link)
    assert seen["text"] == link
    assert seen["format"] == Qt.TextFormat.PlainText


def test_last_choice_is_highlighted():
    colors = {}

    def look(dialog):
        for b in buttons(dialog):
            # A spot of the background, left of the icon.
            colors[b.text()] = b.grab().toImage().pixelColor(12, b.height() // 2).name()

    drive(look, last="yandex")
    last = colors.pop("Yandex")
    assert len(set(colors.values())) == 1
    assert last not in colors.values()


@pytest.fixture
def icon_theme(tmp_path):
    """A theme with one icon, internet-web-browser, entirely red."""
    directory = tmp_path / "kbctest" / "96x96" / "apps"
    directory.mkdir(parents=True)
    (tmp_path / "kbctest" / "index.theme").write_text(
        "[Icon Theme]\nName=kbctest\nComment=test\nDirectories=96x96/apps\n\n[96x96/apps]\nSize=96\nType=Fixed\n")
    image = QImage(96, 96, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    image.save(str(directory / "internet-web-browser.png"))
    before = QIcon.themeSearchPaths(), QIcon.themeName()
    QIcon.setThemeSearchPaths([str(tmp_path)])
    QIcon.setThemeName("kbctest")
    yield
    QIcon.setThemeSearchPaths(before[0])
    QIcon.setThemeName(before[1])


@pytest.mark.parametrize("icon", ["/nonexistent/icon.png", "no-such-icon", ""])
def test_missing_icon_gets_the_default(icon_theme, icon):
    seen = []

    def look(dialog):
        pixmap = button(dialog, "Firefox").icon().pixmap(96, 96)
        seen.append(None if pixmap.isNull() else pixmap.toImage().pixelColor(48, 48).name())

    drive(look, tiles=[Tile("firefox", "Firefox", icon, ("firefox", "%u"))])
    assert seen == ["#ff0000"]


def test_desktop_file_name():
    seen = []
    drive(lambda d: seen.append(QGuiApplication.desktopFileName()))
    assert seen == ["kde-browser-chooser"]


def test_ampersand_in_a_title_is_not_a_shortcut():
    shortcuts = []
    drive(lambda d: shortcuts.extend(b.shortcut().toString() for b in buttons(d)),
          tiles=[Tile("rb", "R&B", "", ("x", "%u"))])
    assert shortcuts == ["", ""]


class FakeExtras(QObject):
    """KWaylandExtras: answers with the token in 20 ms; None means it never answers."""

    xdgActivationTokenArrived = pyqtSignal(int, str)

    def __init__(self, token):
        super().__init__()
        self.token, self.requests = token, []

    def lastInputSerial(self, handle):
        return 42

    def requestXdgActivationToken(self, handle, serial, app_id):
        self.requests.append((handle, serial, app_id))
        if self.token is not None:
            QTimer.singleShot(20, lambda: self.xdgActivationTokenArrived.emit(serial, self.token))


@pytest.fixture
def extras(monkeypatch):
    def install(token):
        fake = FakeExtras(token)
        monkeypatch.setenv("XDG_ACTIVATION_TOKEN", "old")
        monkeypatch.setattr(activation, "kwayland_extras", lambda: fake)
        return fake

    return install


def test_browser_gets_a_fresh_token(extras):
    fake, handles = extras("fresh"), []

    def pick(dialog):
        handles.append(dialog.windowHandle())
        click(dialog, "Firefox")

    assert drive(pick) == FIREFOX
    assert os.environ["XDG_ACTIVATION_TOKEN"] == "fresh"
    assert fake.requests == [(handles[0], 42, "")]


@pytest.mark.parametrize("token", [None, ""])
def test_no_fresh_token_does_not_lose_the_click(extras, token):
    extras(token)
    assert drive(lambda d: click(d, "Firefox")) == FIREFOX
    assert os.environ["XDG_ACTIVATION_TOKEN"] == "old"


def broken():
    raise OSError("libKF6WindowSystem.so.6: no such file")


def test_broken_kde_library_does_not_lose_the_click(extras, monkeypatch):
    extras(None)
    monkeypatch.setattr(activation, "kwayland_extras", broken)
    assert drive(lambda d: click(d, "Firefox")) == FIREFOX


def test_token_that_cannot_be_used_does_not_lose_the_click(extras, monkeypatch):
    """The environment takes no null byte. An exception out of a slot would abort the program; here the hook
    catches it instead."""
    escaped = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, error, trace: escaped.append(error))
    extras("fresh\0token")
    assert drive(lambda d: click(d, "Firefox")) == FIREFOX
    assert escaped == [] and os.environ["XDG_ACTIVATION_TOKEN"] == "old"


class DeadStream:
    """A stderr nobody reads any more."""

    def write(self, text):
        raise BrokenPipeError

    flush = write


def test_dead_stderr_does_not_lose_the_click(extras, monkeypatch):
    extras(None)
    monkeypatch.setattr(activation, "kwayland_extras", broken)

    def pick(dialog):
        stderr, sys.stderr = sys.stderr, DeadStream()
        try:
            click(dialog, "Firefox")
        finally:
            sys.stderr = stderr

    assert drive(pick) == FIREFOX


@pytest.mark.parametrize("title", ["Copy link", "Cancel"])
def test_copy_and_cancel_need_no_token(extras, title):
    fake = extras("fresh")
    drive(lambda d: click(d, title))
    assert fake.requests == []


def test_second_click_while_waiting_is_ignored(extras):
    extras(None)

    def two_clicks(dialog):
        click(dialog, "Firefox")
        click(dialog, "Opera")

    assert drive(two_clicks) == FIREFOX


def test_escape_while_waiting_cancels(extras):
    extras(None)

    def change_mind(dialog):
        click(dialog, "Firefox")
        QTest.keyClick(dialog, Qt.Key.Key_Escape)

    assert drive(change_mind) is None


def test_no_kwayland_extras_off_wayland():
    assert activation.kwayland_extras() is None


def test_kwayland_extras_signatures(monkeypatch):
    """The methods are called by name through the meta-object: they must stay what we think they are."""
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "wayland"))
    try:
        meta = activation.kwayland_extras().metaObject()
    except OSError:
        pytest.skip("no libKF6WindowSystem here")
    methods = {meta.method(i).methodSignature().data().decode() for i in range(meta.methodCount())}
    assert {"requestXdgActivationToken(QWindow*,uint32_t,QString)", "lastInputSerial(QWindow*)",
            "xdgActivationTokenArrived(int,QString)"} <= methods
