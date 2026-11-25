import pytest

from kde_browser_chooser.fallback import pick_with_kdialog
from kde_browser_chooser.model import Tile

CHROME = Tile("chrome", "Google Chrome", "", ("chrome", "%U"))
OPERA = Tile("opera", "Opera", "", ("opera", "%U"))
STRINGS = {"title": "Open link"}


def pick(label="https://e.com/", last="chrome"):
    return pick_with_kdialog([CHROME, OPERA], label, last, STRINGS)


def test_menu(fakes):
    fakes.add("kdialog", out="opera\n")
    assert pick("https://e.com/?a=1&b=<2>") == OPERA
    args = fakes.args("kdialog")
    assert args[:2] == ["--title", "Open link"]
    assert "https://e.com/?a=1&amp;b=&lt;2&gt;" in args
    assert args[-4:] == ["chrome", "Google Chrome", "opera", "Opera"]


def test_cursor_is_on_the_last_choice(fakes):
    fakes.add("kdialog", out="opera\n")
    pick(last="opera")
    args = fakes.args("kdialog")
    assert args[args.index("--default") + 1] == "Opera"  # kdialog compares titles, not tags


def test_cancel(fakes):
    fakes.add("kdialog", code=1)
    assert pick() is None


@pytest.mark.parametrize("code", [2, 127])
def test_failure_is_not_a_cancel(fakes, code):
    fakes.add("kdialog", code=code)
    with pytest.raises(RuntimeError):
        pick()


def test_no_kdialog(fakes):
    with pytest.raises(OSError):
        pick()


def test_long_link(fakes):
    fakes.add("kdialog", out="opera\n")
    pick("x" * 200)
    assert "x" * 107 + "..." in fakes.args("kdialog")
