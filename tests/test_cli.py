import os
import pkgutil
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
CHROME = dict(Type="Application", Name="Google Chrome", Exec="chrome %U", Icon="chrome",
              MimeType="x-scheme-handler/https;")


@pytest.fixture
def session(tmp_path, apps, env, monkeypatch):
    """A desktop session with two browsers and nothing of the real user's."""
    apps.add("chrome", **CHROME)
    apps.add("firefox", **{**CHROME, "Name": "Firefox", "Name[ru]": "Лиса", "Exec": "firefox %u", "Icon": "firefox"})
    env |= {"XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_STATE_HOME": str(tmp_path / "state"),
            "LANG": "en_US.UTF-8"}
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

    def run(argv, picked):
        run.shown, run.done = [], []

        def pick(tiles, label, last, strings):
            run.shown.append((tiles, label, last, strings))
            if isinstance(picked, Exception):
                raise picked
            return next((tile for tile in tiles if tile.id == picked), None)

        monkeypatch.setattr(cli.window, "pick", pick)
        monkeypatch.setattr(cli.actions, "launch", lambda tile, urls, s: run.done.append((tile.id, urls)) or 0)
        monkeypatch.setattr(cli.actions, "copy", lambda urls, s: run.done.append(("copy", urls)) or 0)
        return cli.main(argv)

    return run


def test_opens_and_remembers(run, last):
    last.parent.mkdir(parents=True)
    last.write_text("firefox\n")
    assert run(["--", URL, "u2"], "chrome") == 0
    (tiles, label, shown_last, strings), = run.shown
    assert [tile.id for tile in tiles] == ["copy", "firefox", "chrome"]
    assert (label, shown_last, strings["title"]) == (f"{URL} (+1)", "firefox", "Open link")
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
    assert run.shown[0][1] == URL


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
    assert fakes.args("notify-send")[-2:] == ["Could not show the browser chooser", URL]


def test_config_applies(run, configure):
    configure('language = "ru"\norder = ["chrome"]\nhide = ["copy"]\nrename = { chrome = "Хром" }\n'
              '[[tile]]\nname = "Mine"\ncommand = "mine"\n')
    run([URL], None)
    (tiles, _, _, strings), = run.shown
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


CHILD = f"import sys; sys.path.insert(0, {str(SRC)!r}); from kde_browser_chooser.cli import run; run()"


def test_dead_stderr_still_shows_kdialog(session, fakes):
    fakes.add("kdialog", code=1)
    read_end, dead = os.pipe()
    os.close(read_end)
    # -S hides dist-packages, where PyQt6 lives.
    subprocess.run([sys.executable, "-B", "-S", "-c", CHILD, URL], stderr=dead, timeout=20)
    os.close(dead)
    assert len(fakes.calls("kdialog")) == 1


def test_ctrl_c_ends_the_program(session):
    pytest.importorskip("PyQt6.QtWidgets")
    ready = session / "ready"
    child = (f"import sys; sys.path.insert(0, {str(SRC)!r})\n"
             "from PyQt6.QtCore import QTimer\nfrom PyQt6.QtWidgets import QApplication\n"
             "app = QApplication(['x'])\n"
             f"QTimer.singleShot(200, lambda: open({str(ready)!r}, 'w').close())\n"
             "from kde_browser_chooser.cli import run; run()\n")
    process = subprocess.Popen([sys.executable, "-B", "-c", child, URL])
    deadline = time.monotonic() + 10
    while not ready.exists():
        assert time.monotonic() < deadline
        time.sleep(0.02)
    process.send_signal(signal.SIGINT)
    assert process.wait(1) == -signal.SIGINT


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
