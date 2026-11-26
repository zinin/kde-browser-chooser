import os
from collections.abc import Mapping
from pathlib import Path

APP = "kde-browser-chooser"


def _base(env: Mapping[str, str], variable: str, default: str) -> Path:
    value = env.get(variable, "")
    return Path(value) if os.path.isabs(value) else Path(env.get("HOME") or Path.home(), default)


def config_file(env: Mapping[str, str]) -> Path:
    return _base(env, "XDG_CONFIG_HOME", ".config") / APP / "config.toml"


def last_file(env: Mapping[str, str]) -> Path:
    return _base(env, "XDG_STATE_HOME", ".local/state") / APP / "last"
