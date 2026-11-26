import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import fake_desktop
import kde_browser_chooser
from kde_browser_chooser import desktop as desktop_entry

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "install.sh"
APP = "kde-browser-chooser"
OURS = f"{APP}.desktop"
MIMES = ["x-scheme-handler/http", "x-scheme-handler/https", "text/html", "application/xhtml+xml"]
CORE = ("sh awk cat chmod cmp cp curl cut grep head ln mkdir mktemp mv readlink rm rmdir sed sha256sum tr uname").split()
ALL_OURS = dict.fromkeys([*MIMES, "kdeglobals"], OURS)
ALL_CHROME = dict.fromkeys([*MIMES, "kdeglobals"], "chrome.desktop")

FAKES = {
    "id": "echo 1000",  # CI runs the tests as root
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
        for name in ("xdg-settings", "xdg-mime", "kwriteconfig6"):
            (self.bin / name).symlink_to(ROOT / "tests/fake_desktop.py")
        for name in FAKES:
            self.fake(name)
        self.set("pyqt6")
        self.answers = root / "answers"
        self.env = {"HOME": str(self.home), "PATH": str(self.bin), "REGISTRY": str(self.registry),
                    "XDG_CURRENT_DESKTOP": "KDE", "KBC_BASE_URL": f"file://{dist}", "KBC_TTY": str(self.answers),
                    "KBC_PYTHON": str(self.bin / "python"), "KBC_SYSROOT": str(root / "sysroot")}

    @property
    def desktop(self):
        return fake_desktop.Desktop(self.env)

    def fake(self, name, body=None):
        (self.bin / name).unlink(missing_ok=True)
        (self.bin / name).write_text(f"#!/bin/sh\n{body or FAKES[name]}\n")
        (self.bin / name).chmod(0o755)

    def remove(self, *names):
        for name in names:
            (self.bin / name).unlink()

    def set(self, key, value=""):
        (self.registry / key).write_text(f"{value}\n")

    def unset(self, key):
        (self.registry / key).unlink()

    def get(self, key):
        try:
            return (self.registry / key).read_text().strip()
        except FileNotFoundError:
            return ""

    def choose(self, values):
        """What the user chose in System Settings."""
        groups = fake_desktop.read(self.desktop.mimeapps)
        chosen = groups.setdefault(fake_desktop.DEFAULTS, {})
        for key, value in values.items():
            if key == "kdeglobals":
                self.desktop.browser(value)
            elif value:
                chosen[key] = value
        fake_desktop.write(self.desktop.mimeapps, groups)

    def defaults(self):
        """The user's explicit choices."""
        values = dict(fake_desktop.read(self.desktop.mimeapps).get(fake_desktop.DEFAULTS, {}))
        return values | ({"kdeglobals": self.desktop.browser()} if self.desktop.browser() else {})

    def traces(self):
        return [path.name for path in (self.desktop.mimeapps, self.desktop.kdeglobals)
                if path.exists() and OURS in path.read_text()]

    def add_entry(self, name):
        path = self.desktop.apps / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Desktop Entry]\nExec=/bin/sh %U\n")

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
        return self.desktop.apps / OURS

    @property
    def previous(self):
        return self.home / ".local/state" / APP / "previous-defaults"


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, "-B", ROOT / "tools/build.py", "--out", out], check=True, capture_output=True)
    return out


@pytest.fixture
def fresh(tmp_path, dist):
    """A user who never chose a browser."""
    home = Home(tmp_path, dist)
    for name in ("chrome.desktop", "firefox.desktop", "kate.desktop"):
        home.add_entry(name)
    return home


@pytest.fixture
def home(fresh):
    """A user who chose Chrome for everything."""
    fresh.choose(ALL_CHROME)
    return fresh


def test_installs_and_becomes_the_default(home, dist):
    assert home.run(answers="y\n") == 0, home.output
    assert home.program.read_bytes() == (dist / APP).read_bytes()
    assert home.program.stat().st_mode & 0o777 == 0o755
    assert f"Exec={home.program} -- %U" in home.entry.read_text().splitlines()
    assert home.defaults() == ALL_OURS
    assert f"{APP} {kde_browser_chooser.__version__}" in home.output and "is the default browser now" in home.output


@pytest.mark.parametrize("kind", ["system", "other", None])
def test_becomes_the_default_where_none_was_chosen(fresh, kind):
    """Registering our entry alone can make it the effective default, and that must not count."""
    if kind:
        fresh.set(kind, "chrome.desktop")
    assert fresh.run(answers="y\n") == 0, fresh.output
    assert fresh.defaults() == ALL_OURS
    assert "Make it the default browser?" in fresh.output


@pytest.mark.parametrize("kind", ["system", "other", None])
def test_uninstall_leaves_nothing_where_none_was_chosen(fresh, kind):
    if kind:
        fresh.set(kind, "chrome.desktop")
    fresh.run("--yes")
    assert fresh.run("--uninstall") == 0, fresh.output
    assert fresh.defaults() == {} and fresh.traces() == []
    assert fresh.desktop.effective(MIMES[1]) == ("chrome.desktop" if kind else "")
    assert ("System Settings" in fresh.output) is (kind is None)


def test_enter_means_yes(home):
    home.run(answers="\n")
    assert home.defaults() == ALL_OURS


@pytest.mark.parametrize("answers", ["n\n", ""], ids=["no", "Ctrl+D"])
def test_answer_no(home, answers):
    assert home.run(answers=answers) == 0
    assert home.program.exists() and home.defaults() == ALL_CHROME and not home.previous.exists()


def test_no_default_option(home):
    assert home.run("--no-default", answers="y\n") == 0
    assert home.program.exists() and home.defaults() == ALL_CHROME


@pytest.mark.parametrize("options, env, answers", [
    (["--no-default"], {}, ""), ([], {}, "n\n"), ([], {"KBC_TTY": "/nonexistent"}, "")],
    ids=["--no-default", "no", "no terminal"])
def test_not_becoming_the_default_keeps_the_browser(fresh, options, env, answers):
    """Chrome is merely installed, so our entry in the user's own directory would take its place."""
    fresh.set("other", "chrome.desktop")
    fresh.env |= env
    assert fresh.run(*options, answers=answers) == 0, fresh.output
    assert [fresh.desktop.effective(mime) for mime in MIMES] == ["chrome.desktop"] * len(MIMES)
    assert fresh.defaults() == dict.fromkeys(MIMES, "chrome.desktop")
    assert fresh.output.count("kept chrome.desktop as the default browser;") == 1


@pytest.mark.parametrize("kind", ["system", None])
def test_a_browser_that_stays_effective_needs_no_keeping(fresh, kind):
    if kind:
        fresh.set(kind, "chrome.desktop")
    assert fresh.run("--no-default") == 0, fresh.output
    assert not fresh.desktop.mimeapps.exists() and "kept" not in fresh.output


def test_becoming_the_default_keeps_nothing(fresh):
    fresh.set("other", "chrome.desktop")
    assert fresh.run("--yes") == 0, fresh.output
    assert fresh.defaults() == ALL_OURS and "kept" not in fresh.output


def test_an_explicit_choice_stays_as_it_was(home):
    before = home.desktop.mimeapps.read_bytes()
    assert home.run("--no-default") == 0, home.output
    assert home.desktop.mimeapps.read_bytes() == before and "kept" not in home.output


def test_kept_lines_change_no_other_line(fresh, tmp_path):
    fresh.set("other", "chrome.desktop")
    text = "# mine\n[Added Associations]\nimage/png=gimp.desktop;\n\n[Default Applications]\nimage/png=gwenview.desktop\n"
    real = tmp_path / "dotfiles-mimeapps"
    real.write_text(text)
    fresh.desktop.mimeapps.parent.mkdir(parents=True)
    fresh.desktop.mimeapps.symlink_to(real)
    assert fresh.run("--no-default") == 0, fresh.output
    assert fresh.desktop.mimeapps.is_symlink()
    assert [line for line in real.read_text().splitlines() if not line.endswith("=chrome.desktop")] == text.splitlines()
    assert fresh.defaults() == {"image/png": "gwenview.desktop", **dict.fromkeys(MIMES, "chrome.desktop")}


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


def test_an_update_that_does_not_run_leaves_the_old_program(home, dist, tmp_path):
    home.run("--yes")
    before = home.program.read_bytes()
    broken = shutil.copytree(dist, tmp_path / "broken")
    (broken / APP).write_text("#!/bin/sh\nexit 1\n")
    sums = subprocess.run(["sha256sum", APP, OURS], cwd=broken, capture_output=True, text=True).stdout
    (broken / "SHA256SUMS").write_text(sums)
    home.env["KBC_BASE_URL"] = f"file://{broken}"
    assert home.run("--yes") != 0
    assert "does not run" in home.output and home.program.read_bytes() == before
    assert [path.name for path in home.program.parent.iterdir()] == [APP]


def test_truncated_script_does_nothing(home, tmp_path):
    text = SCRIPT.read_text()
    for part in (0.3, 0.6, 0.9, 0.99):
        (tmp_path / "part.sh").write_text(text[:int(len(text) * part)])
        home.run("--yes", script=tmp_path / "part.sh")
        assert not home.program.exists() and home.defaults() == ALL_CHROME


def test_uninstall_restores_exactly(home):
    chosen = ALL_CHROME | {"text/html": "kate.desktop;chrome.desktop;", "kdeglobals": "!/usr/bin/some-browser"}
    home.choose(chosen)
    home.run("--yes")
    assert home.defaults() == ALL_OURS
    assert home.run("--uninstall") == 0, home.output
    assert home.defaults() == chosen and home.traces() == []
    assert not home.program.exists() and not home.entry.exists() and not home.previous.parent.exists()
    assert "System Settings" not in home.output


def test_uninstall_restores_only_what_is_still_ours(home):
    home.run("--yes")
    own = {"text/html": "kate.desktop", "kdeglobals": "firefox.desktop"}
    home.choose(own)
    home.run("--uninstall")
    assert home.defaults() == ALL_CHROME | own


def test_reinstall_keeps_previous_defaults(home):
    home.run("--yes")
    home.run("--yes")
    home.run("--uninstall")
    assert home.defaults() == ALL_CHROME


def test_previous_defaults_follow_the_user(home):
    """Installed, then the user chose Firefox, then installed again: Firefox comes back."""
    home.run("--yes")
    home.choose({MIMES[0]: "firefox.desktop", MIMES[1]: "firefox.desktop", "kdeglobals": "firefox.desktop"})
    home.run("--yes")
    assert home.defaults() == ALL_OURS
    home.run("--uninstall")
    assert home.defaults() == ALL_CHROME | {MIMES[0]: "firefox.desktop", MIMES[1]: "firefox.desktop",
                                            "kdeglobals": "firefox.desktop"}


def test_other_settings_are_untouched(home):
    home.desktop.mimeapps.write_text("# mine\n[Added Associations]\nimage/png=gimp.desktop;\n\n[Default Applications]\n"
                                     "image/png=gwenview.desktop\n\n[Removed Associations]\nimage/png=x.desktop;\n")
    home.run("--yes")
    home.run("--uninstall")
    groups = fake_desktop.read(home.desktop.mimeapps)
    assert groups[fake_desktop.ADDED] == {"image/png": "gimp.desktop;"}
    assert groups[fake_desktop.DEFAULTS] == {"image/png": "gwenview.desktop"}
    assert groups["[Removed Associations]"] == {"image/png": "x.desktop;"}


@pytest.mark.parametrize("relative", [False, True])
def test_linked_settings_stay_linked(home, tmp_path, relative):
    """xdg-utils write a new mimeapps.list beside the old one and rename it over a link."""
    real = tmp_path / "dotfiles-mimeapps"
    home.desktop.mimeapps.rename(real)
    link = os.path.relpath(real, home.desktop.mimeapps.parent) if relative else str(real)
    home.desktop.mimeapps.symlink_to(link)
    assert home.run("--yes") == 0, home.output
    assert os.readlink(home.desktop.mimeapps) == link
    assert fake_desktop.read(real)[fake_desktop.DEFAULTS] == dict.fromkeys(MIMES, OURS)
    home.run("--uninstall")
    assert os.readlink(home.desktop.mimeapps) == link and home.defaults() == ALL_CHROME


def test_a_link_that_cannot_be_put_back_is_told(home, tmp_path):
    """xdg-utils have turned the link into a file, and the list it pointed to cannot be written."""
    real = tmp_path / "dotfiles-mimeapps"
    home.desktop.mimeapps.rename(real)
    home.desktop.mimeapps.symlink_to(real)
    (tmp_path / f".dotfiles-mimeapps.{APP}.part").mkdir()  # where the new list would be written
    assert home.run("--yes") == 1
    assert f"cannot write {real}" in home.output


def test_unchanged_settings_are_not_rewritten(home):
    os.utime(home.desktop.mimeapps, ns=(0, 0))
    before = home.desktop.mimeapps.stat()
    assert home.run("--uninstall") == 0, home.output
    after = home.desktop.mimeapps.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_settings_keep_their_permissions(home):
    home.run("--yes")
    home.desktop.mimeapps.chmod(0o640)
    assert home.run("--uninstall") == 0, home.output
    assert home.desktop.mimeapps.stat().st_mode & 0o777 == 0o640 and home.defaults() == ALL_CHROME
    assert [path.name for path in home.desktop.mimeapps.parent.iterdir() if path.name.startswith(".")] == []


@pytest.mark.parametrize("other", [None, "firefox.desktop"])
def test_uninstall_when_the_previous_browser_is_gone(home, other):
    """The choice comes back as it was; KDE then picks another browser, or none."""
    if other:
        home.set("other", other)
    home.run("--yes")
    (home.desktop.apps / "chrome.desktop").unlink()
    assert home.run("--uninstall") == 0
    assert home.defaults() == ALL_CHROME
    assert "System Settings" in home.output and home.traces() == [] and not home.program.exists()


def test_uninstall_restores_a_list_whose_first_entry_is_gone(home):
    chosen = ALL_CHROME | dict.fromkeys(MIMES, "missing.desktop;chrome.desktop;")
    home.choose(chosen)
    home.run("--yes")
    assert home.run("--uninstall") == 0, home.output
    assert home.defaults() == chosen
    assert [home.desktop.effective(mime) for mime in MIMES] == ["chrome.desktop"] * len(MIMES)
    assert "System Settings" not in home.output


def test_uninstall_restores_an_entry_from_a_subdirectory(home):
    home.add_entry("vendor/chrome.desktop")
    chosen = dict.fromkeys([*MIMES, "kdeglobals"], "vendor-chrome.desktop")
    home.choose(chosen)
    home.run("--yes")
    assert home.run("--uninstall") == 0, home.output
    assert home.defaults() == chosen
    assert [home.desktop.effective(mime) for mime in MIMES] == ["vendor-chrome.desktop"] * len(MIMES)
    assert "System Settings" not in home.output


@pytest.mark.parametrize("works", [True, False], ids=["works", "fails"])
@pytest.mark.parametrize("recorded", [True, False], ids=["restored", "deleted"])
def test_uninstall_tells_when_kdeglobals_cannot_change(fresh, recorded, works):
    """BrowserApplication is either restored or deleted; Chrome is installed, so a browser stays effective."""
    fresh.set("other", "chrome.desktop")
    if recorded:
        fresh.choose(ALL_CHROME)
    assert fresh.run("--yes") == 0, fresh.output
    if not works:
        fresh.fake("kwriteconfig6", "exit 1")
    assert fresh.run("--uninstall") == 0, fresh.output
    told = "could not change BrowserApplication in kdeglobals."
    assert fresh.output.count(told) == (0 if works else 1) and ("System Settings" in fresh.output) is not works
    assert works or fresh.output.index(told) < fresh.output.index("System Settings")
    assert not fresh.program.exists() and not fresh.previous.exists()


def test_uninstall_nothing(home):
    assert home.run("--uninstall") == 0
    assert home.defaults() == ALL_CHROME


@pytest.mark.parametrize("options, kept", [(["--uninstall"], True), (["--uninstall", "--purge"], False)])
def test_uninstall_and_settings(home, options, kept):
    config = home.home / ".config" / APP / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("")
    assert home.run("--yes") == 0 and home.program.exists()
    assert home.run(*options) == 0 and not home.program.exists()
    assert config.exists() is kept


@pytest.mark.parametrize("name", ["a b", "user@corp.example", "иван", "50%", "a$b", "a\\b", 'a\\"b', "a\\"])
def test_unusual_home(home, tmp_path, name):
    unusual = tmp_path / name
    home.home.rename(unusual)
    home.home = unusual
    home.env["HOME"] = str(unusual)
    assert home.run("--yes") == 0, home.output
    assert home.defaults() == ALL_OURS
    line = next(line for line in home.entry.read_text().splitlines() if line.startswith("Exec="))
    argv = desktop_entry.parse_exec(line.removeprefix("Exec="), icon="", name="", path="")
    assert argv[-2:] == ("--", "%U") and argv[-3].replace("%%", "%") == f"{unusual}/.local/bin/{APP}"
    assert home.run("--uninstall") == 0 and home.defaults() == ALL_CHROME


def test_xdg_directories(home, tmp_path):
    home.env |= {"XDG_DATA_HOME": str(tmp_path / "d"), "XDG_STATE_HOME": str(tmp_path / "s"),
                 "XDG_CONFIG_HOME": str(tmp_path / "c"), "KBC_INSTALL_DIR": str(tmp_path / "i")}
    assert home.run("--yes") == 0, home.output
    assert (tmp_path / "i" / APP).exists() and (tmp_path / "d/applications" / OURS).exists()
    assert (tmp_path / "s" / APP / "previous-defaults").exists() and home.defaults() == ALL_OURS


def test_relative_install_dir_is_refused(home, tmp_path, monkeypatch):
    """KDE would not find the program by a relative Exec."""
    monkeypatch.chdir(tmp_path)  # where a relative directory would land
    home.env["KBC_INSTALL_DIR"] = "relative/bin"
    assert home.run("--yes") == 1
    assert "KBC_INSTALL_DIR must be an absolute path" in home.output
    assert not (tmp_path / "relative").exists() and not home.entry.exists() and home.defaults() == ALL_CHROME


def test_update_and_uninstall_remember_the_install_dir(home, tmp_path):
    custom = tmp_path / "my bin"
    home.env["KBC_INSTALL_DIR"] = str(custom)
    assert home.run("--yes") == 0, home.output
    del home.env["KBC_INSTALL_DIR"]
    assert home.run("--yes") == 0, home.output
    assert (custom / APP).exists() and not home.program.exists()
    line = next(line for line in home.entry.read_text().splitlines() if line.startswith("Exec="))
    argv = desktop_entry.parse_exec(line.removeprefix("Exec="), icon="", name="", path="")
    assert argv[-3].replace("%%", "%") == f"{custom}/{APP}"
    assert home.run("--uninstall") == 0, home.output
    assert not (custom / APP).exists() and not home.entry.exists() and not home.previous.parent.exists()


def test_a_new_install_dir_takes_the_program_along(home, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    home.env["KBC_INSTALL_DIR"] = str(first)
    assert home.run("--yes") == 0, home.output
    home.env["KBC_INSTALL_DIR"] = str(second)
    assert home.run("--yes") == 0, home.output
    assert (second / APP).exists() and not (first / APP).exists()
    del home.env["KBC_INSTALL_DIR"]
    assert home.run("--uninstall") == 0, home.output
    assert not (second / APP).exists() and not home.program.exists()


@pytest.mark.parametrize("spelling", ["{dir}/", "{dir}/.", "{link}"], ids=["slash", "dot", "link"])
def test_the_same_install_dir_named_otherwise_keeps_the_program(home, tmp_path, spelling):
    real, link = tmp_path / "my bin", tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    home.env["KBC_INSTALL_DIR"] = str(real)
    assert home.run("--yes") == 0, home.output
    home.env["KBC_INSTALL_DIR"] = spelling.format(dir=real, link=link)
    assert home.run("--yes") == 0, home.output
    assert (real / APP).exists() and "moved" not in home.output


def test_no_xdg_settings(home):
    home.remove("xdg-settings")
    assert home.run("--yes") == 0
    assert "System Settings" in home.output and home.program.exists()


def test_default_that_did_not_take(home):
    home.fake("xdg-settings", "exit 4")
    assert home.run("--yes") == 0
    assert "System Settings" in home.output and home.defaults() == ALL_CHROME


def test_default_that_took_only_for_links(home):
    """xdg-settings stops at the first type it cannot set."""
    home.set("html-fails")
    assert home.run("--yes") == 0, home.output
    assert home.defaults() == ALL_CHROME | dict.fromkeys([*MIMES[:2], "application/xhtml+xml"], OURS)
    assert "is the default browser now" not in home.output and "no effect" not in home.output
    assert "text/html kdeglobals" in home.output and "System Settings" in home.output


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
    assert home.get("sudo") and home.program.exists() and home.defaults() == ALL_CHROME


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
    assert home.defaults() == ALL_CHROME


@pytest.mark.parametrize("answer, want", [("", ALL_CHROME), ("y", ALL_OURS)])
def test_with_only_kdialog_the_default_answer_is_no(home, answer, want):
    home.unset("pyqt6")
    home.fake("kdialog", "exit 0")
    assert home.run(answers=f"{answer}\n") == 0
    assert home.defaults() == want


@pytest.mark.parametrize("options, want", [([], ALL_CHROME), (["--yes"], ALL_OURS)])
def test_without_a_terminal(home, options, want):
    home.env["KBC_TTY"] = "/nonexistent"
    home.unset("pyqt6")
    home.fake("apt-get", "exit 0")
    assert home.run(*options) == 0
    assert home.program.exists() and home.defaults() == want
    assert bool(home.get("sudo")) is bool(options)
    assert ("--yes" in home.output) is not bool(options)


def test_root_is_refused(home):
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
    assert home.run("--yes") == 0 and home.defaults() == ALL_OURS


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


@pytest.mark.parametrize("options", [["--oops"], ["--version"], ["extra"], ["--purge"], ["--yes", "--purge"]])
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
