import os
import sys

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.dont_write_bytecode = True


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
