import pytest

from kde_browser_chooser.config import Config
from kde_browser_chooser.model import Tile
from kde_browser_chooser.state import read_last, save_last
from kde_browser_chooser.tiles import build

CHROME = Tile("chrome", "Chrome", "chrome", ("chrome", "%U"))
FIREFOX = Tile("firefox", "Firefox", "firefox", ("firefox", "%u"))
MINE = Tile("mine", "Mine", "", ("mine", "%U"))
STRINGS = {"copy": "Copy link"}


def ids(config=Config(tiles=(MINE,)), has_link=True):
    return [tile.id for tile in build([CHROME, FIREFOX], config, STRINGS, has_link)]


def test_default_order():
    assert ids() == ["copy", "chrome", "firefox", "mine"]


def test_copy_tile():
    copy = build([], Config(), STRINGS, True)[0]
    assert (copy.title, copy.icon, copy.command) == ("Copy link", "edit-copy", None)


def test_order_first_then_the_rest():
    assert ids(Config(order=("firefox", "copy", "gone", "firefox"), tiles=(MINE,))) == [
        "firefox", "copy", "chrome", "mine"]


def test_hide():
    assert ids(Config(hide=frozenset({"copy", "chrome", "gone"}))) == ["firefox"]


def test_rename():
    tiles = build([CHROME, FIREFOX], Config(rename={"firefox": "Лис", "copy": "Copy!", "gone": "x"}), STRINGS, True)
    assert [tile.title for tile in tiles] == ["Copy!", "Chrome", "Лис"]


def test_custom_tile_replaces_browser_with_same_id():
    own = Tile("firefox", "Private", "", ("firefox", "--private-window", "%u"))
    assert build([CHROME, FIREFOX], Config(tiles=(own,)), STRINGS, False) == [CHROME, own]


def test_no_link_no_copy():
    assert ids(has_link=False) == ["chrome", "firefox", "mine"]


def test_last_roundtrip(tmp_path):
    path = tmp_path / "state" / "last"
    save_last(path, "firefox")
    assert path.read_text() == "firefox\n"
    assert read_last(path, [CHROME, FIREFOX]) == "firefox"


@pytest.mark.parametrize("content", [None, b"", b"netscape\n", b"\xff\xfe"])
def test_unknown_last_is_the_first_tile(tmp_path, content):
    path = tmp_path / "last"
    if content is not None:
        path.write_bytes(content)
    assert read_last(path, [CHROME, FIREFOX]) == "chrome"


def test_no_tiles_no_last(tmp_path):
    assert read_last(tmp_path / "last", []) == ""


def test_unwritable_state_is_ignored(tmp_path):
    (tmp_path / "file").write_text("")
    save_last(tmp_path / "file" / "last", "firefox")
