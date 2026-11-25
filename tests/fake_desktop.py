#!/usr/bin/python3 -I
"""xdg-settings, xdg-mime and kwriteconfig6 as they behave on KDE Plasma 6 (xdg-utils 1.2.1).

They work on the files of $HOME. $REGISTRY/system is the browser the distribution chose explicitly,
$REGISTRY/other a browser that is merely installed.
"""
import os
import shutil
import sys
from pathlib import Path

OURS = "kde-browser-chooser.desktop"
DEFAULTS, ADDED = "[Default Applications]", "[Added Associations]"


def read(path):
    groups, group = {}, None
    for line in path.read_text().splitlines() if path.exists() else []:
        if line.startswith("["):
            group = groups.setdefault(line, {})
        elif "=" in line:
            key, _, value = line.partition("=")
            group[key] = value
    return groups


def write(path, groups):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{group}\n" + "".join(f"{k}={v}\n" for k, v in keys.items()) + "\n"
                            for group, keys in groups.items()))


class Desktop:
    def __init__(self, env):
        home = Path(env["HOME"])
        config = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
        self.mimeapps, self.kdeglobals = config / "mimeapps.list", config / "kdeglobals"
        self.apps = Path(env.get("XDG_DATA_HOME") or home / ".local/share") / "applications"
        self.registry = Path(env["REGISTRY"])

    def usable(self, entry):
        """xdg-utils take the first word of Exec for the program, quotes and all."""
        try:
            lines = (self.apps / entry).read_text().splitlines()
        except OSError:
            return False
        command = next(line for line in lines if line.startswith("Exec=")).removeprefix("Exec=")
        return shutil.which(command.split()[0], path="/usr/bin:/bin") is not None

    def effective(self, mime):
        explicit = read(self.mimeapps).get(DEFAULTS, {}).get(mime, "").split(";")
        system, other = (self.registry.joinpath(name).read_text().strip() if self.registry.joinpath(name).exists()
                         else "" for name in ("system", "other"))
        # An entry in the user's directory beats whatever is merely installed.
        for entry in [*explicit, system if mime != "application/xhtml+xml" else "", OURS, other]:
            if entry and self.usable(entry):
                return entry
        return ""

    def set_default(self, entry, mime):
        groups = read(self.mimeapps)
        groups.setdefault(DEFAULTS, {})[mime] = entry
        added = groups.setdefault(ADDED, {})
        added[mime] = "".join(f"{e};" for e in dict.fromkeys([entry, *added.get(mime, "").split(";")]) if e)
        write(self.mimeapps, groups)

    def browser(self, value=None, delete=False):
        groups = read(self.kdeglobals)
        if delete:
            groups.get("[General]", {}).pop("BrowserApplication", None)
        elif value is not None:
            groups.setdefault("[General]", {})["BrowserApplication"] = value
        if delete or value is not None:
            write(self.kdeglobals, groups)
        return groups.get("[General]", {}).get("BrowserApplication", "")

    def set_browser(self, entry):
        for mime in ("x-scheme-handler/http", "x-scheme-handler/https", "text/html"):
            before = self.effective(mime)
            self.set_default(entry, mime)
            if self.effective(mime) != entry:
                self.set_default(before, mime)
                return 4
        self.browser(entry)
        return 0


def main(program, args):
    desktop = Desktop(os.environ)
    match program, args:
        case "xdg-settings", ["get", "default-web-browser"]:
            print(desktop.browser() or desktop.effective("text/html"))
        case "xdg-settings", ["set", "default-web-browser", entry]:
            return desktop.set_browser(entry)
        case "xdg-mime", ["query", "default", mime]:
            print(desktop.effective(mime))
        case "xdg-mime", ["default", entry, mime]:
            desktop.set_default(entry, mime)
        case "kwriteconfig6", ["--file", "kdeglobals", "--group", "General", "--key", "BrowserApplication", *rest]:
            desktop.browser(delete=rest[0] == "--delete", value=rest[-1])
        case _:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[0]).name, sys.argv[1:]))
