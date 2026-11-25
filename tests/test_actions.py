import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kde_browser_chooser import actions, dbus
from kde_browser_chooser.actions import expand
from kde_browser_chooser.model import Tile
from kde_browser_chooser.notify import notify

SRC = Path(__file__).resolve().parent.parent / "src"
URL = "https://e.com/?a=1&b=<2>"
STRINGS = {"copied": "Copied", "copy_failed": "Copy failed", "launch_failed": "No {name}"}


@pytest.mark.parametrize("command, urls, argvs", [
    (("x", "%U"), ["a", "b"], [["x", "a", "b"]]),
    (("x", "%F", "-v"), ["a", "b"], [["x", "a", "b", "-v"]]),
    (("x", "%u"), ["a", "b"], [["x", "a"], ["x", "b"]]),
    (("x", "%f"), ["a"], [["x", "a"]]),
    (("x", "--url=%u"), ["a"], [["x", "--url=a"]]),
    (("x", "--url=%u"), [], [["x", "--url="]]),
    (("x", "%u", "%%"), [], [["x", "%"]]),
    (("x", "%U"), [], [["x"]]),
    (("x", "%%u", "%u"), ["a%20b"], [["x", "%u", "a%20b"]]),
    (("f", "@@u", "%u", "@@"), ["a"], [["f", "@@u", "a", "@@"]])])
def test_expand(command, urls, argvs):
    assert expand(command, urls) == argvs


def run_in_child(tmp_path, command, urls):
    """Calls actions.launch in another process; the fake browser reports to the file "out"."""
    browser = tmp_path / "browser"
    browser.write_text(
        "#!/bin/bash\n"
        f"{{ echo \"$$ $* A=$A token=$XDG_ACTIVATION_TOKEN\"; /usr/bin/grep SigIgn /proc/self/status; }} > '{tmp_path}/'$$.part; /usr/bin/mv '{tmp_path}/'$$.part '{tmp_path}/'$$.out\n")
    browser.chmod(0o755)
    child = (f"import sys\nsys.path.insert(0, {str(SRC)!r})\n"
             "from kde_browser_chooser import actions\nfrom kde_browser_chooser.model import Tile\n"
             f"actions.launch(Tile('x', 'X', '', {tuple(command)!r}), {urls!r}, {{}})\n")
    process = subprocess.Popen([sys.executable, "-B", "-c", child],
                               env={**os.environ, "PATH": f"{tmp_path}:/usr/bin:/bin", "XDG_ACTIVATION_TOKEN": "abc"})
    assert process.wait(10) == 0
    deadline = time.monotonic() + 5
    while len(outs := sorted(tmp_path.glob("*.out"))) < max(1, len(urls) if "%u" in command else 1):
        assert time.monotonic() < deadline, "a browser did not start"
        time.sleep(0.02)
    return process.pid, [out.read_text() for out in outs]


def test_launch_replaces_process(tmp_path):
    pid, (out,) = run_in_child(tmp_path, [str(tmp_path / "browser"), "%U"], ["u1", "u2"])
    first, sigign, *_ = out.splitlines()
    assert first == f"{pid} u1 u2 A= token=abc"
    ignored = int(sigign.split()[1], 16)
    assert not ignored & (1 << 12), "SIGPIPE is still ignored"
    assert not ignored & (1 << 24), "SIGXFSZ is still ignored"


def test_launch_resolves_path_and_wrappers(tmp_path):
    _, (out,) = run_in_child(tmp_path, ["env", "A=b", "browser", "%u"], ["u"])
    assert " u A=b token=abc" in out


def test_two_links_start_two_processes(tmp_path):
    pid, outs = run_in_child(tmp_path, ["browser", "%u"], ["a", "b"])
    by_link = {line.split()[1]: int(line.split()[0]) for line in (out.splitlines()[0] for out in outs)}
    assert by_link["b"] == pid
    assert by_link["a"] != pid


@pytest.mark.parametrize("urls", [["u"], ["u", "v"]])
def test_missing_program_is_reported(fakes, urls):
    fakes.add("notify-send")
    assert actions.launch(Tile("x", "Firefox", "", ("/nonexistent/firefox", "%u")), urls, STRINGS) == 1
    assert fakes.args("notify-send")[-2] == "No Firefox"
    assert "/nonexistent/firefox" in fakes.args("notify-send")[-1]


def test_impossible_command_is_reported(fakes):
    fakes.add("notify-send")
    assert actions.launch(Tile("x", "Firefox", "", ("fire\0fox", "%u")), ["u"], STRINGS) == 1
    assert fakes.args("notify-send")[-2] == "No Firefox"


def test_copy_uses_wl_copy_first(fakes, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    for name in ("wl-copy", "busctl", "notify-send"):
        fakes.add(name)
    assert actions.copy([URL, "b"], STRINGS) == 0
    assert fakes.stdin("wl-copy") == f"{URL}\nb".encode()
    assert fakes.calls("busctl") == []
    assert fakes.args("notify-send")[-2:] == ["Copied", f"{URL}\nb"]


@pytest.mark.parametrize("wl_copy", [None, 1])
def test_copy_falls_back_to_klipper(fakes, monkeypatch, wl_copy):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    if wl_copy is not None:
        fakes.add("wl-copy", code=wl_copy)
    for name in ("busctl", "notify-send"):
        fakes.add(name)
    assert actions.copy([URL], STRINGS) == 0
    assert fakes.args("busctl") == ["--user", "--", "call", "org.kde.klipper", "/klipper",
                                    "org.kde.klipper.klipper", "setClipboardContents", "s", URL]


def test_copy_on_x11_uses_klipper(fakes, monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    for name in ("wl-copy", "busctl", "notify-send"):
        fakes.add(name)
    assert actions.copy([URL], STRINGS) == 0
    assert fakes.calls("wl-copy") == [] and len(fakes.calls("busctl")) == 1


def test_copy_failure_is_reported(fakes, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    fakes.add("wl-copy", code=1)
    fakes.add("notify-send")
    assert actions.copy([URL], STRINGS) == 1
    assert [call[-2] for call in fakes.calls("notify-send")] == ["Copy failed"]


def test_invalid_utf8_is_copied_as_is(fakes, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    for name in ("wl-copy", "notify-send"):
        fakes.add(name)
    actions.copy([os.fsdecode(b"https://e.com/\xff")], STRINGS)
    assert fakes.stdin("wl-copy") == b"https://e.com/\xff"


def test_notify(fakes):
    fakes.add("notify-send")
    notify("edit-copy", "--Summary", "Body")
    assert fakes.args("notify-send") == ["-a", "Browser Chooser", "-h", "string:desktop-entry:kde-browser-chooser",
                                         "-i", "edit-copy", "--", "--Summary", "Body"]


@pytest.mark.parametrize("broken", [None, 1])
def test_notify_falls_back_to_dbus(fakes, broken):
    if broken is not None:
        fakes.add("notify-send", code=broken)
    fakes.add("busctl")
    notify("edit-copy", "Summary", "Body")
    assert fakes.args("busctl") == [
        "--user", "--", "call", "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications", "Notify", "susssasa{sv}i",
        "Browser Chooser", "0", "edit-copy", "Summary", "Body", "0", "0", "10000"]


def test_notify_never_raises(fakes, capsys):
    notify("edit-copy", "Summary", "Body")
    assert "Summary" in capsys.readouterr().err


def test_notify_shows_what_it_can(fakes):
    fakes.add("notify-send")
    notify("edit-copy", "Summary", "nu\0ll")
    assert fakes.args("notify-send")[-2:] == ["Summary", "null"]


def test_gdbus_without_busctl(fakes):
    fakes.add("gdbus")
    assert dbus.call("a.b", "/c", "d.e", "Do", ("s", "it's a \\ b"), ("u", "0"), ("as", ""), ("a{sv}", ""), ("i", "5"))
    assert fakes.args("gdbus") == ["call", "--session", "--dest", "a.b", "--object-path", "/c", "--method", "d.e.Do",
                                   "--", "'it\\'s a \\\\ b'", "uint32 0", "@as []", "@a{sv} {}", "int32 5"]


def test_dbus_failure(fakes):
    assert not dbus.call("a", "/b", "c", "D")
    fakes.add("busctl", code=1)
    assert not dbus.call("a", "/b", "c", "D")
