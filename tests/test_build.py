import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import kde_browser_chooser

ROOT = Path(__file__).resolve().parent.parent


def build(out):
    subprocess.run([sys.executable, "-B", ROOT / "tools/build.py", "--out", out], check=True, capture_output=True)
    return out


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    return build(tmp_path_factory.mktemp("dist"))


def test_files(dist):
    assert {file.name for file in dist.iterdir()} == {"kde-browser-chooser", "kde-browser-chooser.desktop", "SHA256SUMS"}
    assert (dist / "kde-browser-chooser").stat().st_mode & 0o777 == 0o755
    assert (dist / "kde-browser-chooser").read_bytes().startswith(b"#!/usr/bin/python3 -I\n")


def test_sums_match(dist):
    for line in (dist / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((dist / name).read_bytes()).hexdigest() == digest
    assert len((dist / "SHA256SUMS").read_text().splitlines()) == 2


def test_reproducible(dist, tmp_path):
    again = build(tmp_path / "again")
    for file in dist.iterdir():
        assert (again / file.name).read_bytes() == file.read_bytes()


def test_runs_isolated(dist, tmp_path):
    (tmp_path / "tomllib.py").write_text("raise SystemExit('poisoned')")
    out = subprocess.run([dist / "kde-browser-chooser", "--version"], cwd=tmp_path, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONHOME": "/nonexistent"})
    assert (out.stdout, out.stderr) == (f"kde-browser-chooser {kde_browser_chooser.__version__}\n", "")


def test_speaks_russian_from_the_archive(dist, tmp_path):
    out = subprocess.run([dist / "kde-browser-chooser", "--list"], capture_output=True, text=True, check=True,
                         env={"PATH": os.environ["PATH"], "HOME": str(tmp_path), "LANG": "ru_RU.UTF-8"})
    assert out.stdout.startswith("copy\tСкопировать ссылку\t")


def test_desktop_entry(dist):
    entry = (dist / "kde-browser-chooser.desktop").read_text().splitlines()
    for line in ("[Desktop Entry]", "Type=Application", "Name=Browser Chooser", "Name[ru]=Выбор браузера",
                 "Comment=Choose a browser for every link",
                 "Comment[ru]=Спрашивает, в каком браузере открыть ссылку", "Exec=@EXEC@ -- %U",
                 "Icon=internet-web-browser", "Terminal=false", "Categories=Network;WebBrowser;",
                 "MimeType=x-scheme-handler/http;x-scheme-handler/https;text/html;application/xhtml+xml;"):
        assert line in entry


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="no desktop-file-validate")
def test_desktop_entry_is_valid(dist, tmp_path):
    entry = tmp_path / "kde-browser-chooser.desktop"
    entry.write_text((dist / "kde-browser-chooser.desktop").read_text().replace("@EXEC@", "/usr/bin/true"))
    assert subprocess.run(["desktop-file-validate", entry], capture_output=True, text=True).stdout == ""


def test_replaced_under_an_open_window(dist, tmp_path):
    """The update lands while the window is open; the choice must still reach the browser."""
    pytest.importorskip("PyQt6.QtWidgets")
    archive, update = tmp_path / "kde-browser-chooser", tmp_path / "update"
    shutil.copy(dist / "kde-browser-chooser", archive)
    update.write_bytes(b"#!/usr/bin/python3 -I\n" + os.urandom(5000))
    browser = tmp_path / "browser"
    browser.write_text(f'#!/bin/sh\necho "$@" > "{tmp_path}/opened"\n')
    browser.chmod(0o755)
    entry = tmp_path / "data/applications/fake.desktop"
    entry.parent.mkdir(parents=True)
    entry.write_text(f"[Desktop Entry]\nType=Application\nName=Fake\nExec={browser} %u\n"
                     "MimeType=x-scheme-handler/https;\n")
    driver = f"""
import os, sys
sys.path.insert(0, {str(archive)!r})
from kde_browser_chooser import cli, desktop
desktop.EXTRA_DATA_DIRS = ()
real = cli.window.pick
def pick(*args):
    global app
    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QToolButton
    app = QApplication(["test"])
    def update_and_click():
        os.replace({str(update)!r}, {str(archive)!r})
        for widget in app.allWidgets():
            if isinstance(widget, QToolButton) and widget.text() == "Fake":
                QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
                return
    QTimer.singleShot(700, update_and_click)
    QTimer.singleShot(5000, lambda: os._exit(9))
    return real(*args)
cli.window.pick = pick
sys.exit(cli.main(["--", "https://e.com/"]))
"""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen", "LANG": "C.UTF-8",
           "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_DATA_DIRS": str(tmp_path / "none")}
    result = subprocess.run([sys.executable, "-I", "-c", driver], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "opened").read_text() == "https://e.com/\n"
