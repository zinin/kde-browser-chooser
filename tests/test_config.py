from pathlib import Path

import pytest

from kde_browser_chooser import paths
from kde_browser_chooser.config import Config, ConfigError, load
from kde_browser_chooser.model import Tile

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"


@pytest.fixture
def write(tmp_path):
    def write(text):
        path = tmp_path / "config.toml"
        path.write_text(text)
        return path

    return write


def test_example_file_loads():
    config = load(EXAMPLE)
    assert config.language and config.order and config.hide and config.rename and config.tiles


def test_no_file_and_empty_file(tmp_path, write):
    assert load(tmp_path / "absent.toml") == Config()
    assert load(write("")) == Config()


def test_everything(write):
    config = load(write('''
        language = "ru"
        order = ["copy", "firefox"]
        hide = ["opera"]
        rename = { "yandex-browser" = "Яндекс" }
        [[tile]]
        id = "work"
        name = "Chrome: работа"
        icon = "google-chrome"
        command = "chrome --profile-directory='Profile 1'"
    '''))
    assert config == Config("ru", ("copy", "firefox"), frozenset({"opera"}), {"yandex-browser": "Яндекс"},
                            (Tile("work", "Chrome: работа", "google-chrome",
                                  ("chrome", "--profile-directory=Profile 1", "%U")),))


@pytest.mark.parametrize("text, named", [
    ('hide = "opera"', "hide"), ("order = [1]", "order"), ("oops = 1", "oops"), ('language = "xx"', "xx"),
    ("language = 1", "language"), ("rename = []", "rename"), ("rename = { a = 1 }", "rename"),
    ("tile = 1", "tile"), ('[[tile]]\nname = "x"', "command"), ('[[tile]]\ncommand = "x"', "name"),
    ('[[tile]]\nname = "x"\ncommand = "x"\nicno = "y"', "icno"),
    ('[[tile]]\nid = "copy"\nname = "x"\ncommand = "x"', "copy"),
    ('[[tile]]\nid = "cancel"\nname = "x"\ncommand = "x"', "cancel"),
    ('[[tile]]\nname = "x"\ncommand = "\'"', "command"), ('[[tile]]\nname = "x"\ncommand = ""', "command"),
    ('[[tile]]\nname = "x"\ncommand = "a"\n[[tile]]\nname = "X"\ncommand = "b"', "x"),
    ("order = [1 2]", "line 1")])
def test_bad_config(write, text, named):
    with pytest.raises(ConfigError, match=named):
        load(write(text))


def test_unreadable_config(tmp_path):
    (tmp_path / "dir.toml").mkdir()
    with pytest.raises(ConfigError):
        load(tmp_path / "dir.toml")


def test_not_utf8(tmp_path):
    (tmp_path / "config.toml").write_bytes(b'language = "\xff"')
    with pytest.raises(ConfigError):
        load(tmp_path / "config.toml")


def test_too_deep(write, monkeypatch):
    def loads(_):
        raise RecursionError("too deep")

    monkeypatch.setattr("tomllib.loads", loads)
    with pytest.raises(ConfigError, match="too deep"):
        load(write(""))


def test_bom_is_accepted(write):
    assert load(write("\ufeffhide = []")) == Config()


@pytest.mark.parametrize("command, want", [
    ("x", ("x", "%U")), ('x --p "a b"', ("x", "--p", "a b", "%U")), ("x %u", ("x", "%u")),
    ("x --url=%u -v", ("x", "--url=%u", "-v")), ("x 100%%", ("x", "100%%", "%U"))])
def test_command(write, command, want):
    assert load(write(f"[[tile]]\nname = 'n'\ncommand = '{command}'")).tiles[0].command == want


def test_id_comes_from_the_name(write):
    assert load(write("[[tile]]\nname = 'Chrome: Работа 2'\ncommand = 'x'")).tiles[0].id == "chrome-работа-2"


def test_icon_is_optional(write):
    assert load(write("[[tile]]\nname = 'n'\ncommand = 'x'")).tiles[0].icon == ""


@pytest.mark.parametrize("env, config, last", [
    ({"HOME": "/h"}, "/h/.config/kde-browser-chooser/config.toml", "/h/.local/state/kde-browser-chooser/last"),
    ({"HOME": "/h", "XDG_CONFIG_HOME": "/c", "XDG_STATE_HOME": "/s"},
     "/c/kde-browser-chooser/config.toml", "/s/kde-browser-chooser/last")])
def test_paths(env, config, last):
    assert paths.config_file(env) == Path(config)
    assert paths.last_file(env) == Path(last)
