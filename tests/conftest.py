import os
import sys
from pathlib import Path

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.dont_write_bytecode = True

# kdialog's QCommandLineParser takes an argument that starts with "-" before "--" for an option, and an
# unknown option ends kdialog with 1, which is also "Cancel".
KDIALOG_OPTIONS = """\
while [ $# -gt 0 ] && [ "$1" != -- ]; do
    case $1 in
    --title | --icon | --default | --menu) shift ;;
    -?*) exit 1 ;;
    esac
    shift
done
"""


class Apps:
    """Writes desktop entries into temporary XDG data directories."""

    def __init__(self, root):
        self.user = root / "user-data"
        self.system = root / "system-data"

    def path(self, entry_id, system=True):
        path = (self.system if system else self.user) / "applications" / f"{entry_id}.desktop"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def add(self, entry_id, system=True, **fields):
        lines = [f"{key}={value}" for key, value in fields.items() if value is not None]
        self.path(entry_id, system).write_text("\n".join(["[Desktop Entry]", *lines, ""]))


@pytest.fixture
def apps(tmp_path):
    return Apps(tmp_path)


@pytest.fixture
def env(tmp_path, apps, monkeypatch):
    """An environment that sees only the temporary data directories."""
    from kde_browser_chooser import desktop

    monkeypatch.setattr(desktop, "EXTRA_DATA_DIRS", ())
    return {"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin", "XDG_CURRENT_DESKTOP": "KDE",
            "XDG_DATA_HOME": str(apps.user), "XDG_DATA_DIRS": str(apps.system)}


class Fakes:
    """Fake external commands that record their arguments and stdin; nothing else is in PATH."""

    def __init__(self, root):
        self.root = root
        self.bin = root / "fake-bin"
        self.bin.mkdir()

    def add(self, name, out="", code=0):
        script = self.bin / name
        script.write_text(
            "#!/bin/bash\n"
            f"{{ for a in \"$@\"; do printf '%s\\0' \"$a\"; done; printf '\\001'; }} >> '{self.root}/{name}.calls'\n"
            + (f"/usr/bin/cat > '{self.root}/{name}.stdin'\n" if name == "wl-copy" else "")
            + (KDIALOG_OPTIONS if name == "kdialog" else "")
            + f"printf '%s' '{out}'\nexit {code}\n")
        script.chmod(0o755)

    def calls(self, name):
        try:
            text = (self.root / f"{name}.calls").read_text()
        except FileNotFoundError:
            return []
        return [call.split("\0")[:-1] for call in text.split("\1")[:-1]]

    def args(self, name):
        return self.calls(name)[-1]

    def stdin(self, name):
        return (self.root / f"{name}.stdin").read_bytes()


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    fakes = Fakes(tmp_path)
    monkeypatch.setenv("PATH", str(fakes.bin))
    return fakes


@pytest.fixture
def gone():
    """Tells whether a process has ended. One that ended stays a zombie until its parent reaps it, and the
    parent it gets when its own dies may never do that: in a CI container PID 1 is "tail -f /dev/null"."""

    def gone(pid):
        try:
            stat = Path("/proc", str(pid), "stat").read_text()
        except (FileNotFoundError, ProcessLookupError):
            return True
        return stat[stat.rindex(")") + 1:].split()[0] in ("Z", "X")

    return gone
