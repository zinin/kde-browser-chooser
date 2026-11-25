import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "install.sh"
APP = "kde-browser-chooser"
OURS = f"{APP}.desktop"
KEYS = ["x-scheme-handler/http", "x-scheme-handler/https", "text/html", "application/xhtml+xml", "kdeglobals"]
CORE = ("sh awk cat chmod cp curl cut grep head id mkdir mktemp mv rm sed sha256sum tr uname").split()

FAKES = {
    # What xdg-settings does on KDE: http, https, text/html and kdeglobals.
    "xdg-settings": """
        [ "$2" = default-web-browser ] || exit 2
        case $1 in
        get) cat "$REGISTRY/kdeglobals" 2>/dev/null || echo ;;
        set) for key in x-scheme-handler_http x-scheme-handler_https text_html kdeglobals; do
                echo "$3" > "$REGISTRY/$key"; done ;;
        esac""",
    "xdg-mime": """
        case $1 in
        query) cat "$REGISTRY/$(echo "$3" | tr / _)" 2>/dev/null || true ;;
        default) echo "$2" > "$REGISTRY/$(echo "$3" | tr / _)" ;;
        esac""",
    "kreadconfig6": 'cat "$REGISTRY/kdeglobals" 2>/dev/null || echo',
    "kwriteconfig6": 'for last; do :; done; echo "$last" > "$REGISTRY/kdeglobals"',
    "plasmashell": "exit 0",
    "sudo": 'echo "sudo $*" >> "$REGISTRY/sudo"; [ -e "$REGISTRY/sudo-fails" ] || : > "$REGISTRY/pyqt6"',
    "python": """
        case "$3" in
        *version_info*) [ ! -e "$REGISTRY/old-python" ] ;;
        *PyQt6*) [ -e "$REGISTRY/pyqt6" ] ;;
        esac""",
}


class Home:
    """A user with a fake desktop: only the listed commands exist."""

    def __init__(self, root, dist):
        self.home, self.bin, self.registry = root / "home", root / "bin", root / "registry"
        for directory in (self.home, self.bin, self.registry):
            directory.mkdir()
        for name in CORE:
            (self.bin / name).symlink_to(shutil.which(name))
        for name in FAKES:
            self.fake(name)
        self.set("pyqt6")
        self.answers = root / "answers"
        self.env = {"HOME": str(self.home), "PATH": str(self.bin), "REGISTRY": str(self.registry),
                    "XDG_CURRENT_DESKTOP": "KDE", "KBC_BASE_URL": f"file://{dist}", "KBC_TTY": str(self.answers),
                    "KBC_PYTHON": str(self.bin / "python"), "KBC_SYSROOT": str(root / "sysroot")}

    def fake(self, name, body=None):
        (self.bin / name).write_text(f"#!/bin/sh\n{body or FAKES[name]}\n")
        (self.bin / name).chmod(0o755)

    def remove(self, *names):
        for name in names:
            (self.bin / name).unlink()

    def set(self, key, value=""):
        (self.registry / key.replace("/", "_")).write_text(f"{value}\n")

    def unset(self, key):
        (self.registry / key).unlink()

    def get(self, key):
        try:
            return (self.registry / key.replace("/", "_")).read_text().strip()
        except FileNotFoundError:
            return ""

    def defaults(self):
        return [self.get(key) for key in KEYS]

    def add_entry(self, name):
        path = self.home / ".local/share/applications" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Desktop Entry]\n")

    def run(self, *options, answers="", script=SCRIPT):
        self.answers.write_text(answers)
        result = subprocess.run(["/bin/sh", script, *options], env=self.env, capture_output=True, text=True, timeout=30,
                                stdin=subprocess.DEVNULL)
        self.output = result.stdout + result.stderr
        return result.returncode

    @property
    def program(self):
        return self.home / ".local/bin" / APP

    @property
    def entry(self):
        return self.home / ".local/share/applications" / OURS

    @property
    def previous(self):
        return self.home / ".local/state" / APP / "previous-defaults"


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, "-B", ROOT / "tools/build.py", "--out", out], check=True, capture_output=True)
    return out


@pytest.fixture
def home(tmp_path, dist):
    home = Home(tmp_path, dist)
    for key in KEYS:
        home.set(key, "chrome.desktop")
    home.add_entry("chrome.desktop")
    return home


def test_installs_and_becomes_the_default(home, dist):
    assert home.run(answers="y\n") == 0, home.output
    assert home.program.read_bytes() == (dist / APP).read_bytes()
    assert home.program.stat().st_mode & 0o777 == 0o755
    assert f"Exec={home.program} -- %U" in home.entry.read_text().splitlines()
    assert home.defaults() == [OURS] * 5
    assert f"{APP} 0.1.0" in home.output


def test_enter_means_yes(home):
    home.run(answers="\n")
    assert home.defaults() == [OURS] * 5


def test_answer_no(home):
    assert home.run(answers="n\n") == 0
    assert home.program.exists() and home.defaults() == ["chrome.desktop"] * 5 and not home.previous.exists()


def test_no_default_option(home):
    assert home.run("--no-default", answers="y\n") == 0
    assert home.program.exists() and home.defaults() == ["chrome.desktop"] * 5


def test_bad_checksum_installs_nothing(home, dist, tmp_path):
    broken = shutil.copytree(dist, tmp_path / "broken")
    with open(broken / APP, "ab") as file:
        file.write(b"x")
    home.env["KBC_BASE_URL"] = f"file://{broken}"
    assert home.run("--yes") != 0
    assert "SHA256SUMS" in home.output
    assert not home.program.exists() and not home.entry.exists()


def test_download_failure_installs_nothing(home):
    home.env["KBC_BASE_URL"] = "file:///nonexistent"
    assert home.run("--yes") != 0
    assert "cannot download file:///nonexistent/SHA256SUMS" in home.output
    assert not home.program.exists()


def test_truncated_script_does_nothing(home, tmp_path):
    text = SCRIPT.read_text()
    for part in (0.3, 0.6, 0.9, 0.99):
        (tmp_path / "part.sh").write_text(text[:int(len(text) * part)])
        home.run("--yes", script=tmp_path / "part.sh")
        assert not home.program.exists() and home.defaults() == ["chrome.desktop"] * 5


def test_previous_defaults_saved_per_type(home):
    home.set("text/html", "kate.desktop")
    home.unset("application_xhtml+xml")
    home.run("--yes")
    assert home.previous.read_text() == (
        "x-scheme-handler/http=chrome.desktop\nx-scheme-handler/https=chrome.desktop\n"
        "text/html=kate.desktop\nkdeglobals=chrome.desktop\n")


def test_reinstall_keeps_previous_defaults(home):
    home.run("--yes")
    before = home.previous.read_text()
    home.run("--yes")
    assert home.previous.read_text() == before


def test_previous_defaults_follow_the_user(home):
    """Installed, then the user chose Firefox, then installed again: Firefox comes back."""
    home.run("--yes")
    for key in ("x-scheme-handler/http", "x-scheme-handler/https", "kdeglobals"):
        home.set(key, "firefox.desktop")
    home.run("--yes")
    assert home.previous.read_text() == (
        "x-scheme-handler/http=firefox.desktop\nx-scheme-handler/https=firefox.desktop\n"
        "text/html=chrome.desktop\napplication/xhtml+xml=chrome.desktop\nkdeglobals=firefox.desktop\n")


def test_uninstall_restores_what_is_still_ours(home):
    home.run("--yes")
    home.set("text/html", "kate.desktop")
    assert home.run("--uninstall") == 0, home.output
    assert home.defaults() == ["chrome.desktop", "chrome.desktop", "kate.desktop", "chrome.desktop", "chrome.desktop"]
    assert not home.program.exists() and not home.entry.exists() and not home.previous.parent.exists()


def test_uninstall_when_the_previous_browser_is_gone(home):
    home.run("--yes")
    (home.home / ".local/share/applications/chrome.desktop").unlink()
    assert home.run("--uninstall") == 0
    assert "System Settings" in home.output and not home.program.exists()


def test_uninstall_without_records(home):
    home.run("--yes")
    home.previous.unlink()
    assert home.run("--uninstall") == 0
    assert "System Settings" in home.output and not home.program.exists()


def test_uninstall_nothing(home):
    assert home.run("--uninstall") == 0
    assert home.defaults() == ["chrome.desktop"] * 5


@pytest.mark.parametrize("options, kept", [(["--uninstall"], True), (["--uninstall", "--purge"], False)])
def test_uninstall_and_settings(home, options, kept):
    config = home.home / ".config" / APP / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("")
    assert home.run("--yes") == 0 and home.program.exists()
    assert home.run(*options) == 0 and not home.program.exists()
    assert config.exists() is kept


def test_home_with_a_space(home, tmp_path):
    spaced = tmp_path / "a b"
    home.home.rename(spaced)
    home.home = spaced
    home.env["HOME"] = str(spaced)
    assert home.run("--yes") == 0, home.output
    assert f'Exec="{spaced}/.local/bin/{APP}" -- %U' in home.entry.read_text().splitlines()
    assert home.defaults() == [OURS] * 5
    assert home.run("--uninstall") == 0 and not home.program.exists()


def test_xdg_directories(home, tmp_path):
    home.env |= {"XDG_DATA_HOME": str(tmp_path / "d"), "XDG_STATE_HOME": str(tmp_path / "s"),
                 "KBC_INSTALL_DIR": str(tmp_path / "i")}
    assert home.run("--yes") == 0, home.output
    assert (tmp_path / "i" / APP).exists() and (tmp_path / "d/applications" / OURS).exists()
    assert (tmp_path / "s" / APP / "previous-defaults").exists()


def test_no_xdg_settings(home):
    home.remove("xdg-settings")
    assert home.run("--yes") == 0
    assert "System Settings" in home.output and home.program.exists()


def test_default_that_did_not_take(home):
    home.fake("xdg-settings", "case $1 in get) echo other.desktop;; esac")
    assert home.run("--yes") == 0
    assert "System Settings" in home.output


@pytest.mark.parametrize("manager, command", [
    ("apt-get", "sudo apt-get install -y python3-pyqt6"), ("dnf", "sudo dnf install -y python3-pyqt6"),
    ("pacman", "sudo pacman -S --needed --noconfirm python-pyqt6"),
    ("zypper", "sudo zypper --non-interactive install python3-PyQt6")])
@pytest.mark.parametrize("answer", ["y", "", "n"])
def test_offers_pyqt6(home, manager, command, answer):
    home.unset("pyqt6")
    home.fake(manager, "exit 0")
    assert home.run(answers=f"{answer}\nn\n") == 0
    assert command.removeprefix("sudo ") in home.output
    assert home.get("sudo") == ("" if answer == "n" else command)


def test_no_package_manager(home):
    home.unset("pyqt6")
    assert home.run("--yes") == 0
    assert "PyQt6" in home.output and home.get("sudo") == "" and home.program.exists()


def test_package_that_did_not_install(home):
    home.unset("pyqt6")
    home.set("sudo-fails")
    home.fake("apt-get", "exit 0")
    assert home.run("--yes") == 0
    assert home.get("sudo") and home.program.exists() and home.defaults() == ["chrome.desktop"] * 5


def test_ostree_only_prints(home, tmp_path):
    home.unset("pyqt6")
    home.fake("dnf", "exit 0")
    (tmp_path / "sysroot/run").mkdir(parents=True)
    (tmp_path / "sysroot/run/ostree-booted").touch()
    assert home.run("--yes") == 0
    assert "rpm-ostree install python3-pyqt6" in home.output and home.get("sudo") == ""


def test_without_window_and_list_it_is_never_the_default(home):
    home.unset("pyqt6")
    assert home.run("--yes", answers="y\ny\n") == 0
    assert home.defaults() == ["chrome.desktop"] * 5


@pytest.mark.parametrize("answer, want", [("", "chrome.desktop"), ("y", OURS)])
def test_with_only_kdialog_the_default_answer_is_no(home, answer, want):
    home.unset("pyqt6")
    home.fake("kdialog", "exit 0")
    assert home.run(answers=f"{answer}\n") == 0
    assert home.defaults() == [want] * 5


@pytest.mark.parametrize("options, want", [([], "chrome.desktop"), (["--yes"], OURS)])
def test_without_a_terminal(home, options, want):
    home.env["KBC_TTY"] = "/nonexistent"
    home.unset("pyqt6")
    home.fake("apt-get", "exit 0")
    assert home.run(*options) == 0
    assert home.program.exists() and home.defaults() == [want] * 5
    assert bool(home.get("sudo")) is bool(options)
    assert ("--yes" in home.output) is not bool(options)


def test_root_is_refused(home):
    home.remove("id")
    home.fake("id", "echo 0")
    assert home.run("--yes") != 0
    assert "root" in home.output
    assert not home.program.exists()


def test_other_systems_are_refused(home):
    home.remove("uname")
    home.fake("uname", "echo FreeBSD")
    assert home.run("--yes") != 0
    assert "Linux" in home.output
    assert not home.program.exists()


def test_old_python_is_refused(home):
    home.set("old-python")
    assert home.run("--yes") != 0
    assert "3.11" in home.output and not home.program.exists()


@pytest.mark.parametrize("answers, installed", [("n\n", False), ("\n", False), ("y\nn\n", True)])
def test_not_kde_warns_and_asks(home, answers, installed):
    home.env["XDG_CURRENT_DESKTOP"] = "GNOME"
    home.remove("plasmashell")
    home.run(answers=answers)
    assert "KDE" in home.output and home.program.exists() is installed


def test_plasma_without_session_variable(home):
    del home.env["XDG_CURRENT_DESKTOP"]
    assert home.run("--yes") == 0 and home.defaults() == [OURS] * 5


def test_update_asks_nothing_already_done(home):
    home.run("--yes")
    home.program.write_text("old")
    home.env["KBC_TTY"] = "/nonexistent"
    assert home.run() == 0
    assert "--yes" not in home.output and home.program.read_bytes().startswith(b"#!/usr/bin/python3 -I")


def test_replaces_the_file_atomically(home):
    home.run("--yes")
    home.program.write_text("old")
    inode = home.program.stat().st_ino
    with open(home.program) as opened:
        home.run("--yes")
        assert opened.read() == "old"
    assert home.program.stat().st_ino != inode
    assert [path.name for path in home.program.parent.iterdir()] == [APP]


@pytest.mark.parametrize("options, env, url", [
    ([], {}, "releases/latest/download/SHA256SUMS"), (["--version", "9.9"], {}, "releases/download/v9.9/SHA256SUMS"),
    ([], {"KBC_VERSION": "v9.9"}, "releases/download/v9.9/SHA256SUMS")])
def test_release_address(home, options, env, url):
    del home.env["KBC_BASE_URL"]
    home.env |= env
    home.remove("curl")
    home.fake("curl", 'echo "$*" >> "$REGISTRY/curl"; exit 22')
    assert home.run("--yes", *options) != 0
    assert f"https://github.com/zinin/{APP}/{url}" in home.get("curl")


@pytest.mark.parametrize("options", [["--oops"], ["--version"], ["extra"]])
def test_bad_options(home, options):
    assert home.run(*options) != 0
    assert "Usage" in home.output and not home.program.exists()


def test_help(home):
    assert home.run("--help") == 0
    assert "--uninstall" in home.output and not home.program.exists()


def test_path_hint(home):
    home.run("--yes")
    assert "PATH" in home.output
    home.env["PATH"] += f":{home.program.parent}"
    home.run("--yes")
    assert "PATH" not in home.output


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="no shellcheck")
def test_shellcheck():
    result = subprocess.run(["shellcheck", "-s", "sh", SCRIPT], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
