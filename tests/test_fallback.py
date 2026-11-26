import pytest

from kde_browser_chooser.fallback import pick_with_kdialog
from kde_browser_chooser.model import Tile

CHROME = Tile("chrome", "Google Chrome", "", ("chrome", "%U"))
OPERA = Tile("opera", "Opera", "", ("opera", "%U"))
STRINGS = {"title": "Open link"}


def pick(label="https://e.com/", last="chrome", counter="", tiles=(CHROME, OPERA)):
    return pick_with_kdialog(list(tiles), label, counter, last, STRINGS)


def test_menu(fakes):
    fakes.add("kdialog", out="opera\n")
    assert pick("https://e.com/?a=1&b=<2>") == OPERA
    args = fakes.args("kdialog")
    assert args[:2] == ["--title", "Open link"]
    assert "<qt>https://e.com/?a=1&amp;b=&lt;2&gt;</qt>" in args  # as rich text, so that < > & show as such
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
    assert "<qt>" + "x" * 107 + "...</qt>" in fakes.args("kdialog")


def test_long_link_keeps_the_counter(fakes):
    fakes.add("kdialog", out="opera\n")
    pick("x" * 200, counter="(+1)")
    assert "<qt>" + "x" * 102 + "... (+1)</qt>" in fakes.args("kdialog")


def test_items_that_look_like_options(fakes):
    tiles = [Tile("-p", "- private", "", ("x", "%U")), Tile("--help", "-v", "", ("x", "%U"))]
    fakes.add("kdialog", out="-p\n")
    assert pick(tiles=tiles, last="--help") == tiles[0]
    args = fakes.args("kdialog")
    assert args[args.index("--") + 1:] == ["-p", "- private", "--help", "-v"]


def test_id_with_a_trailing_space(fakes):
    work = Tile("work ", "Work", "", ("x", "%U"))
    fakes.add("kdialog", out="work \n")
    assert pick(tiles=[CHROME, work]) == work


@pytest.mark.parametrize("out", ["", "nonexistent\n", "Usage: kdialog [options]\n"])
def test_unknown_answer_is_not_a_cancel(fakes, out):
    fakes.add("kdialog", out=out)
    with pytest.raises(RuntimeError):
        pick()
