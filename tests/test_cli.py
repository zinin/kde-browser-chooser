import os
import pkgutil
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import kde_browser_chooser
from kde_browser_chooser import cli

SRC = Path(__file__).resolve().parent.parent / "src"
URL = "https://e.com/?a=1&b=<2>"
SHOWN = "https://e.com/?a=1&amp;b=&lt;2&gt;"  # URL in a notification, which Plasma reads as markup
CHROME = dict(Type="Application", Name="Google Chrome", Exec="chrome %U", Icon="chrome",
              MimeType="x-scheme-handler/https;")


@pytest.fixture
def session(tmp_path, apps, env, fakes, monkeypatch):
    """A desktop session with two browsers and nothing of the real user's: only fake programs are on PATH."""
    apps.add("chrome", **CHROME)
    apps.add("firefox", **{**CHROME, "Name": "Firefox", "Name[ru]": "Лиса", "Exec": "firefox %u", "Icon": "firefox"})
    env |= {"XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_STATE_HOME": str(tmp_path / "state"),
            "LANG": "en_US.UTF-8", "PATH": str(fakes.bin)}
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return tmp_path


@pytest.fixture
def configure(session):
    def configure(text):
        path = session / "config" / "kde-browser-chooser" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text(text)

    return configure


@pytest.fixture
def last(session):
    return session / "state" / "kde-browser-chooser" / "last"


@pytest.fixture
def run(session, monkeypatch):
    """Runs main(); picked is a tile id, None for "Cancel", or an exception of the window."""

    def run(argv, picked, token=None):
        run.shown, run.done = [], []

        def show(function, tiles, label, counter, last, strings):
            assert function is cli.show_window
            run.shown.append((tiles, label, counter, last, strings))
            if isinstance(picked, Exception):
                raise picked
            return [picked, token]

        monkeypatch.setattr(cli.child, "run", show)
        monkeypatch.setattr(cli.actions, "launch", lambda tile, urls, s: run.done.append((tile.id, urls)) or 0)
        monkeypatch.setattr(cli.actions, "copy", lambda urls, s: run.done.append(("copy", urls)) or 0)
        return cli.main(argv)

    return run


def test_nothing_reaches_the_real_session(session):
    """A broken window falls back to kdialog and notifications: in a test they must be fakes, and nothing a test
    starts may find the user's display or session bus."""
    assert [name for name in ("kdialog", "notify-send", "busctl", "gdbus", "wl-copy") if shutil.which(name)] == []
    assert not {"DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"} & set(os.environ)
    assert not Path(os.environ["XDG_RUNTIME_DIR"], "bus").exists()


def test_opens_and_remembers(run, last):
    last.parent.mkdir(parents=True)
    last.write_text("firefox\n")
    assert run(["--", URL, "u2"], "chrome") == 0
    (tiles, label, counter, shown_last, strings), = run.shown
    assert [tile.id for tile in tiles] == ["copy", "firefox", "chrome"]
    assert (label, counter, shown_last, strings["title"]) == (URL, "(+1)", "firefox", "Open link")
    assert run.done == [("chrome", [URL, "u2"])]
    assert last.read_text() == "chrome\n"


def test_copy(run, last):
    assert run([URL], "copy") == 0
    assert run.done == [("copy", [URL])]
    assert last.read_text() == "copy\n"


def test_cancel(run, last):
    assert run([URL], None) == 0
    assert run.done == [] and not last.exists()


def test_without_link(run):
    run([], "firefox")
    (tiles, label, *_), = run.shown
    assert label == "(no link)" and [tile.id for tile in tiles] == ["firefox", "chrome"]
    assert run.done == [("firefox", [])]


def test_one_link_has_no_counter(run):
    run([URL], None)
    assert run.shown[0][1:3] == (URL, "")


def test_long_first_link_keeps_the_counter(run, fakes):
    long = "https://e.com/" + "x" * 300
    fakes.add("kdialog", code=1)
    run([long, "u2"], ImportError("no PyQt6"))
    assert run.shown[0][1:3] == (long, "(+1)")
    args = fakes.args("kdialog")
    assert args[args.index("--menu") + 1] == "<qt>" + long[:102] + "... (+1)</qt>"


def test_control_characters_show_as_replacement_characters(run, fakes):
    """The label stays one line; the browser gets the link as it came."""
    link = "https://e.com/a\nb\tc\x1bd"
    shown = "https://e.com/a�b�c�d"
    fakes.add("kdialog", out="chrome\n")
    run([link, "u2"], ImportError("no PyQt6"))
    assert run.shown[0][1:3] == (shown, "(+1)")
    args = fakes.args("kdialog")
    assert args[args.index("--menu") + 1] == f"<qt>{shown} (+1)</qt>"
    assert run.done == [("chrome", [link, "u2"])]


def test_browser_gets_the_token_of_the_window(run, monkeypatch):
    monkeypatch.setenv("XDG_ACTIVATION_TOKEN", "old")
    run([URL], "chrome", token="fresh")
    assert os.environ["XDG_ACTIVATION_TOKEN"] == "fresh"


@pytest.mark.parametrize("picked", ["chrome", None])
def test_window_returns_id_and_token(monkeypatch, picked):
    def pick(tiles, *_):
        os.environ["XDG_ACTIVATION_TOKEN"] = "fresh"
        return tiles[0] if picked else None

    monkeypatch.setenv("XDG_ACTIVATION_TOKEN", "old")
    monkeypatch.setattr(cli.window, "pick", pick)
    tile = cli.Tile("chrome", "Chrome", "", ("chrome", "%U"))
    assert cli.show_window([tile], "", "", "", {}) == [picked, "fresh"]


def test_crashed_window_falls_back(session, monkeypatch, fakes):
    """Not even a crash in C++ loses the link."""
    opened = []
    fakes.add("kdialog", out="firefox\n")
    monkeypatch.setattr(cli.window, "pick", lambda *_: os.kill(os.getpid(), signal.SIGKILL))
    monkeypatch.setattr(cli.actions, "launch", lambda tile, urls, s: opened.append((tile.id, urls)) or 0)
    assert cli.main([URL]) == 0
    assert opened == [("firefox", [URL])]


def test_qt_without_a_display_falls_back(session, fakes):
    """Qt calls abort() then."""
    pytest.importorskip("PyQt6.QtWidgets")
    fakes.add("kdialog", code=1)
    code = f"import resource; resource.setrlimit(resource.RLIMIT_CORE, (1, 1)); {CHILD}"  # no core dump
    result = subprocess.run([sys.executable, "-B", "-c", code, URL], timeout=20, capture_output=True, text=True,
                            env={**os.environ, "QT_QPA_PLATFORM": "nonexistent"})
    assert result.returncode == 0, result.stderr
    assert len(fakes.calls("kdialog")) == 1


def test_anything_unexpected_is_told_with_the_link(run, fakes, monkeypatch):
    fakes.add("notify-send")

    def broken(*_):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(cli.desktop, "find_browsers", broken)
    assert run([URL], None) == 1
    assert fakes.args("notify-send")[-2:] == ["Could not show the browser chooser", SHOWN]


def test_falls_back_to_kdialog(run, fakes, last):
    fakes.add("kdialog", out="firefox\n")
    assert run([URL], ImportError("no PyQt6")) == 0
    assert run.done == [("firefox", [URL])] and last.read_text() == "firefox\n"


def test_kdialog_cancel(run, fakes):
    fakes.add("kdialog", code=1)
    assert run([URL], ImportError("no PyQt6")) == 0
    assert run.done == []


@pytest.mark.parametrize("code", [2, 127, None])
def test_nothing_works_so_notify(run, fakes, code):
    if code is not None:
        fakes.add("kdialog", code=code)
    fakes.add("notify-send")
    assert run([URL], ImportError("no PyQt6")) == 1
    assert fakes.args("notify-send")[-2:] == ["Could not show the browser chooser", SHOWN]


def test_unknown_answer_of_kdialog_is_told_with_the_link(run, fakes):
    fakes.add("kdialog", out="Usage: kdialog [options]\n")
    fakes.add("notify-send")
    assert run([URL], ImportError("no PyQt6")) == 1
    assert fakes.args("notify-send")[-2:] == ["Could not show the browser chooser", SHOWN]


def test_config_applies(run, configure):
    configure('language = "ru"\norder = ["chrome"]\nhide = ["copy"]\nrename = { chrome = "Хром" }\n'
              '[[tile]]\nname = "Mine"\ncommand = "mine"\n')
    run([URL], None)
    (tiles, _, _, _, strings), = run.shown
    assert [(tile.id, tile.title) for tile in tiles] == [("chrome", "Хром"), ("firefox", "Лиса"), ("mine", "Mine")]
    assert strings["title"] == "Открыть ссылку"


def test_config_error_still_shows_the_window(run, configure, fakes):
    fakes.add("notify-send")
    configure('hide = "chrome"')
    run([URL], "chrome")
    assert [tile.id for tile in run.shown[0][0]] == ["copy", "firefox", "chrome"]
    assert run.done == [("chrome", [URL])]
    summary, body = fakes.args("notify-send")[-2:]
    assert summary == "The settings file has an error and is not used" and "hide" in body


def test_link_code_inside_quotes_is_a_config_error(run, configure, fakes):
    fakes.add("notify-send")
    configure("[[tile]]\nname = 'Mine'\ncommand = \"sh -c 'firefox %u'\"\n")
    run([URL], "chrome")
    assert [tile.id for tile in run.shown[0][0]] == ["copy", "firefox", "chrome"]
    assert run.done == [("chrome", [URL])]
    summary, body = fakes.args("notify-send")[-2:]
    assert summary == "The settings file has an error and is not used" and "a link code inside quotes" in body


@pytest.mark.parametrize("argv, urls", [
    (["--", "u"], ["u"]), (["u"], ["u"]), (["--", "--list"], ["--list"]), (["--list", "u"], ["--list", "u"]),
    (["--x"], ["--x"]), (["u", "--version"], ["u", "--version"]), (["--"], [])])
def test_options_work_only_alone(run, argv, urls):
    run(argv, "chrome")
    assert run.done == [("chrome", urls)]


def test_list(run, configure, capsys):
    configure('hide = ["copy", "chrome"]\n[[tile]]\nname = "Mine"\nicon = "/m.png"\ncommand = "mine \'a b\' %u"\n')
    assert run(["--list"], None) == 0
    assert run.shown == []
    assert capsys.readouterr().out.splitlines() == [
        "copy\tCopy link\t\tedit-copy", "firefox\tFirefox\tfirefox %u\tfirefox",
        "chrome\tGoogle Chrome\tchrome %U\tchrome", "mine\tMine\tmine 'a b' %u\t/m.png"]


def test_list_tells_a_config_error(run, configure, fakes, capsys):
    configure("oops = 1")
    assert run(["--list"], None) == 1
    assert "oops" in capsys.readouterr().err


def test_version(run, capsys):
    assert run(["--version"], None) == 0
    assert capsys.readouterr().out == f"kde-browser-chooser {kde_browser_chooser.__version__}\n"


def test_help(run, capsys):
    assert run(["--help"], None) == 0
    assert "--list" in (out := capsys.readouterr().out) and "config.toml" in out


def test_help_names_the_settings_file(run, session, capsys):
    assert run(["--help"], None) == 0
    assert f"Settings: {session}/config/kde-browser-chooser/config.toml (optional)" in capsys.readouterr().out


CHILD = f"import sys; sys.path.insert(0, {str(SRC)!r}); from kde_browser_chooser.cli import run; run()"


def test_dead_stderr_still_shows_kdialog(session, fakes):
    fakes.add("kdialog", code=1)
    read_end, dead = os.pipe()
    os.close(read_end)
    # -S hides dist-packages, where PyQt6 lives.
    subprocess.run([sys.executable, "-B", "-S", "-c", CHILD, URL], stderr=dead, timeout=20)
    os.close(dead)
    assert len(fakes.calls("kdialog")) == 1


def test_ignored_sigchld_does_not_lose_the_link(session, fakes):
    """The program that opened the link may ignore SIGCHLD, and exec keeps that: then no exit status of a child
    would be seen, and a notify-send that failed would count as shown."""
    fakes.add("kdialog", code=2)
    fakes.add("notify-send", code=1)
    fakes.add("busctl")
    # -S hides dist-packages, where PyQt6 lives: the window cannot open.
    result = subprocess.run([sys.executable, "-B", "-S", "-c", CHILD, URL], capture_output=True, text=True,
                            timeout=20, preexec_fn=lambda: signal.signal(signal.SIGCHLD, signal.SIG_IGN))
    assert result.returncode == 1, result.stderr
    assert len(fakes.calls("kdialog")) == 1
    assert [call[-4] for call in fakes.calls("busctl")] == [SHOWN]  # the body of the notification


def test_ctrl_c_ends_the_program(session, gone):
    pytest.importorskip("PyQt6.QtWidgets")
    ready = session / "ready"
    child = f"""
import os, sys
sys.path.insert(0, {str(SRC)!r})
from kde_browser_chooser import cli, window
real = window.pick
def pick(*args):
    global app
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    app = QApplication(["x"])
    QTimer.singleShot(200, lambda: os.rename({str(ready)!r} + ".part", {str(ready)!r}))
    open({str(ready)!r} + ".part", "w").write(str(os.getpid()))
    return real(*args)
window.pick = pick
cli.run()
"""
    process = subprocess.Popen([sys.executable, "-B", "-c", child, URL], stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while not ready.exists():
        assert time.monotonic() < deadline
        time.sleep(0.02)
    process.send_signal(signal.SIGINT)
    assert process.wait(1) == -signal.SIGINT
    assert "Traceback" not in process.communicate()[1]
    while not gone(ready.read_text()):
        assert time.monotonic() < deadline, "the window is still there"
        time.sleep(0.02)


def test_all_modules_are_loaded_before_the_window():
    # An update replaces the archive under an open window, and then nothing more can be imported from it.
    child = (f"import pkgutil, sys; sys.path.insert(0, {str(SRC)!r})\nimport kde_browser_chooser.cli\n"
             "print(*(n for n in sys.modules if n.startswith('kde_browser_chooser.')))\n"
             "print('PyQt6' in sys.modules)")
    out = subprocess.run([sys.executable, "-B", "-c", child], capture_output=True, text=True, check=True).stdout
    loaded, qt = out.splitlines()
    names = {f"kde_browser_chooser.{m.name}" for m in pkgutil.iter_modules(kde_browser_chooser.__path__)}
    assert names - {"kde_browser_chooser.__main__"} == set(loaded.split())
    assert qt == "False", "without PyQt6 the fallback must still work"
