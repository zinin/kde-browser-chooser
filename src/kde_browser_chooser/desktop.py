"""Finds installed browsers by their desktop entries.

https://specifications.freedesktop.org/desktop-entry-spec/latest/
"""
import os
import re
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path

from .model import Tile

# Searched even when the session's XDG_DATA_DIRS lacks them.
EXTRA_DATA_DIRS = (
    "~/.local/share/flatpak/exports/share",
    "/var/lib/flatpak/exports/share",
    "/var/lib/snapd/desktop",
)
NOT_BROWSERS = {"kde-browser-chooser", "browser-chooser"}  # ourselves and our predecessor
ESCAPES = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
KEPT_CODES = {"%%", "%u", "%U", "%f", "%F"}


def application_dirs(env: Mapping[str, str]) -> list[Path]:
    home = env.get("HOME") or str(Path.home())
    user = env.get("XDG_DATA_HOME") or f"{home}/.local/share"
    system = env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [user, *system.split(":"), *(path.replace("~", home, 1) for path in EXTRA_DATA_DIRS)]
    unique = dict.fromkeys(os.path.normpath(path) for path in dirs if os.path.isabs(path))
    return [Path(path) / "applications" for path in unique]


def unescape(value: str) -> str:
    return re.sub(r"\\([sntr\\])", lambda match: ESCAPES[match[1]], value)


def split_words(text: str) -> list[str]:
    """Splits a command line; single quotes are not in the spec but do occur."""
    words: list[str] = []
    word: str | None = None
    quote = ""
    chars = iter(text)
    for char in chars:
        if quote:
            if char == quote:
                quote = ""
            elif char == "\\" and quote == '"':
                escaped = next(chars, "")
                word += escaped if escaped in '"`$\\' else char + escaped
            else:
                word += char
        elif char in "\"'":
            quote, word = char, word or ""
        elif char.isspace():
            if word is not None:
                words.append(word)
            word = None
        else:
            word = (word or "") + (next(chars, "") if char == "\\" else char)
    if quote:
        raise ValueError("unclosed quote")
    if word is not None:
        words.append(word)
    return words


def parse_exec(value: str, *, icon: str, name: str, path: str) -> tuple[str, ...]:
    """Splits Exec, leaving only %% and the URL codes unexpanded."""
    texts = {"%c": name.replace("%", "%%"), "%k": path.replace("%", "%%"), "%": "%%"}

    def expand(match: re.Match) -> str:
        return match[0] if match[0] in KEPT_CODES else texts.get(match[0], "")

    argv: list[str] = []
    for word in split_words(unescape(value)):
        if word == "%i":
            argv += ["--icon", icon.replace("%", "%%")] if icon else []
            continue
        expanded = re.sub(r"%.?", expand, word, flags=re.DOTALL)
        if expanded or not word:
            argv.append(expanded)
    if not argv:
        raise ValueError("empty command")
    return tuple(argv)


def takes_url(command: tuple[str, ...]) -> bool:
    return any(re.search("%[uUfF]", word.replace("%%", "")) for word in command)


def read_entry(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    fields: dict[str, str] = {}
    in_group = False
    for line in map(str.strip, text.split("\n")):
        if line.startswith("["):
            in_group = line == "[Desktop Entry]"
        elif in_group and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            fields.setdefault(key.strip(), value.strip())
    return fields


def is_visible_browser(fields: Mapping[str, str], env: Mapping[str, str]) -> bool:
    def items(key: str) -> set[str]:
        return {item.strip() for item in fields.get(key, "").split(";") if item.strip()}

    desktops = set((env.get("XDG_CURRENT_DESKTOP") or "KDE").split(":"))
    try_exec = fields.get("TryExec")
    return (
        fields.get("Type") == "Application"
        and "x-scheme-handler/https" in items("MimeType")
        and not any(fields.get(key) == "true" for key in ("NoDisplay", "Hidden", "Terminal"))
        and (not items("OnlyShowIn") or bool(items("OnlyShowIn") & desktops))
        and not items("NotShowIn") & desktops
        and (not try_exec or shutil.which(try_exec, path=env.get("PATH")) is not None)
    )


def browser_tile(entry_id: str, path: Path, env: Mapping[str, str], language: str) -> Tile | None:
    fields = read_entry(path)
    if entry_id in NOT_BROWSERS or not is_visible_browser(fields, env):
        return None
    name = unescape(fields.get(f"Name[{language}]") or fields.get("Name", ""))
    icon = unescape(fields.get("Icon", ""))
    try:
        command = parse_exec(fields.get("Exec", ""), icon=icon, name=name, path=str(path))
    except ValueError:
        return None
    return Tile(entry_id, name, icon, command) if name and takes_url(command) else None


def entries(env: Mapping[str, str]) -> Iterator[tuple[str, Path]]:
    """Yields every entry id once, from the directory that wins."""
    seen = set()
    for top in application_dirs(env):
        for directory, _, files in sorted(os.walk(top)):
            for file in sorted(files):
                path = Path(directory, file)
                entry_id = "-".join(path.relative_to(top).parts).removesuffix(".desktop")
                if file.endswith(".desktop") and entry_id not in seen:
                    seen.add(entry_id)
                    yield entry_id, path


def find_browsers(env: Mapping[str, str], language: str) -> list[Tile]:
    tiles: dict[tuple[str, ...], Tile] = {}
    for entry_id, path in entries(env):
        tile = browser_tile(entry_id, path, env, language)
        if tile:
            tiles.setdefault(tile.command, tile)
    return sorted(tiles.values(), key=lambda tile: (tile.title.casefold(), tile.id))
