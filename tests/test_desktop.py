from pathlib import Path

import pytest

from kde_browser_chooser.desktop import application_dirs, find_browsers, parse_exec, split_marked, split_words
from kde_browser_chooser.model import Tile

FIREFOX = dict(Type="Application", Name="Firefox", Exec="firefox %u", Icon="firefox",
               MimeType="text/html;x-scheme-handler/https;")


def test_browser_found(apps, env):
    apps.add("firefox", **FIREFOX)
    assert find_browsers(env, "en") == [Tile("firefox", "Firefox", "firefox", ("firefox", "%u"))]


@pytest.mark.parametrize("change", [
    {"NoDisplay": "true"}, {"Hidden": "true"}, {"Terminal": "true"}, {"Type": "Link"},
    {"MimeType": "text/html;"}, {"MimeType": None}, {"OnlyShowIn": "GNOME;"}, {"NotShowIn": "XFCE;KDE;"},
    {"TryExec": "/nonexistent"}, {"TryExec": "no-such-program"}, {"Exec": "firefox"},
    {"Exec": '"open %u'}, {"Exec": None}, {"Name": None},
    {"Exec": "sh -c 'run %u'"}, {"Exec": 'sh -c "run %u"'}, {"Exec": "sh -c run\\ %u"}])
def test_not_a_browser(apps, env, change):
    apps.add("firefox", **{**FIREFOX, **change})
    assert find_browsers(env, "en") == []


@pytest.mark.parametrize("change", [
    {"OnlyShowIn": "GNOME;KDE;"}, {"NotShowIn": "GNOME;"}, {"TryExec": "sh"}, {"TryExec": "/bin/sh"},
    {"NoDisplay": "false"}, {"Exec": "browser --app=%u"}, {"Exec": '"/opt/my browser/run" %u'}])
def test_still_a_browser(apps, env, change):
    apps.add("firefox", **{**FIREFOX, **change})
    assert len(find_browsers(env, "en")) == 1


def test_current_desktop_defaults_to_kde(apps, env):
    del env["XDG_CURRENT_DESKTOP"]
    apps.add("firefox", **{**FIREFOX, "OnlyShowIn": "KDE;"})
    assert len(find_browsers(env, "en")) == 1


def test_user_entry_masks_system_one(apps, env):
    apps.add("firefox", **FIREFOX)
    apps.add("firefox", system=False, **{**FIREFOX, "Hidden": "true"})
    assert find_browsers(env, "en") == []


def test_subdirectory_becomes_part_of_id(apps, env):
    apps.add("vendor/firefox", **FIREFOX)
    assert [tile.id for tile in find_browsers(env, "en")] == ["vendor-firefox"]


def test_snap_and_flatpak_dirs_added_once():
    env = {"HOME": "/home/u", "XDG_DATA_DIRS": "/usr/share:/var/lib/snapd/desktop/"}
    dirs = [str(path) for path in application_dirs(env)]
    assert dirs == ["/home/u/.local/share/applications", "/usr/share/applications",
                    "/var/lib/snapd/desktop/applications",
                    "/home/u/.local/share/flatpak/exports/share/applications",
                    "/var/lib/flatpak/exports/share/applications"]


def test_default_data_dirs():
    dirs = application_dirs({"HOME": "/home/u", "XDG_DATA_DIRS": ""})
    assert dirs[:3] == [Path("/home/u/.local/share/applications"), Path("/usr/local/share/applications"),
                        Path("/usr/share/applications")]


def test_same_command_is_one_tile(apps, env):
    chrome = {**FIREFOX, "Name": "Google Chrome", "Exec": "google-chrome %U"}
    apps.add("com.google.Chrome", **chrome)
    apps.add("google-chrome", **chrome)
    assert len(find_browsers(env, "en")) == 1


def test_localized_name(apps, env):
    apps.add("firefox", **{**FIREFOX, "Name[ru]": "Лиса"})
    assert find_browsers(env, "ru")[0].title == "Лиса"
    assert find_browsers(env, "en")[0].title == "Firefox"


def test_excludes_itself_and_the_old_script(apps, env):
    apps.add("kde-browser-chooser", **FIREFOX)
    apps.add("browser-chooser", **{**FIREFOX, "Exec": "other %u"})
    assert find_browsers(env, "en") == []


def test_sorted_by_title(apps, env):
    for name in ("yandex", "Google Chrome", "Firefox"):
        apps.add(name.lower().replace(" ", "-"), **{**FIREFOX, "Name": name, "Exec": f"{name[0]} %u"})
    assert [tile.title for tile in find_browsers(env, "en")] == ["Firefox", "Google Chrome", "yandex"]


def test_other_groups_and_comments_are_skipped(apps, env):
    apps.path("firefox").write_text(
        "# comment\r\n[Desktop Entry]\r\nType=Application\r\nName = Firefox\r\nExec=firefox %u\r\n"
        "MimeType=x-scheme-handler/https\r\n\r\n[Desktop Action new]\r\nName=New Window\r\nNoDisplay=true\r\n")
    assert find_browsers(env, "en") == [Tile("firefox", "Firefox", "", ("firefox", "%u"))]


@pytest.mark.parametrize("data", [b"\xff\xfe\x00", b"", b"[Other]\nExec=x %u\n"])
def test_garbage_is_ignored(apps, env, data):
    apps.path("garbage").write_bytes(data)
    apps.add("firefox", **FIREFOX)
    assert [tile.id for tile in find_browsers(env, "en")] == ["firefox"]


def test_missing_directories_are_fine(env):
    assert find_browsers(env, "en") == []


@pytest.mark.parametrize("value, argv", [
    ("firefox %u", ("firefox", "%u")),
    ('"/opt/a b/x" --new %U', ("/opt/a b/x", "--new", "%U")),
    ("env A=b /snap/bin/firefox %u", ("env", "A=b", "/snap/bin/firefox", "%u")),
    ("x --url=%u", ("x", "--url=%u")),
    ("x %% %c %k %i %u", ("x", "%%", "N", "/p", "--icon", "I", "%u")),
    ("x %d %m --a%n %u", ("x", "--a", "%u")),
    ("flatpak run o @@u %u @@", ("flatpak", "run", "o", "@@u", "%u", "@@")),
    (r'x "a\\"b" "\\$HOME" "\\`" %u', ("x", 'a"b', "$HOME", "`", "%u")),
    (r"x a\sb %u", ("x", "a", "b", "%u")),
    ("x '100%%u' %u", ("x", "100%%u", "%u")),
    ("sh -c 'exec run \"$1\"' sh %u", ("sh", "-c", 'exec run "$1"', "sh", "%u"))])
def test_parse_exec(value, argv):
    assert parse_exec(value, icon="I", name="N", path="/p") == argv


def test_percent_in_name_stays_literal():
    assert parse_exec("x %c %u", icon="", name="100%u", path="/p") == ("x", "100%%u", "%u")


def test_no_icon_no_icon_option():
    assert parse_exec("x %i %u", icon="", name="N", path="/p") == ("x", "%u")


@pytest.mark.parametrize("text, words", [
    ("sh -c 'run %u'", [("sh", False), ("-c", False), ("run %u", True)]),
    ('a "b c"d e\\ f g\\', [("a", False), ("b cd", True), ("e f", True), ("g", True)]),
    ("x %u --app=%u", [("x", False), ("%u", False), ("--app=%u", False)])])
def test_split_marked(text, words):
    """Each word tells whether a part of it was quoted or escaped; the words themselves are those of split_words."""
    assert split_marked(text) == words
    assert split_words(text) == [word for word, _ in words]


# A link code in a word that was quoted or escaped would become part of the text the quotes protect.
@pytest.mark.parametrize("value", ['x "open', "x 'open", "", "sh -c 'run %u'", 'sh -c "run %U"', r"sh -c run\ %u",
                                   "x '%f'", "x pre'fix'%F", r"x \%u"])
def test_parse_exec_rejects(value):
    with pytest.raises(ValueError):
        parse_exec(value, icon="", name="", path="")
