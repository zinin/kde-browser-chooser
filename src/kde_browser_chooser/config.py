"""Reads the optional settings file."""
import re
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .desktop import split_marked, takes_url
from .i18n import AVAILABLE
from .model import Tile

RESERVED_IDS = {"copy", "cancel"}
SHLEX_BLANKS = " \t\r\n"  # where shlex.split parts words
LINK_IN_QUOTES = ("a link code inside quotes is not allowed; pass the link as an argument of its own, "
                  "as in sh -c 'exec firefox \"$1\"' sh %u")


class ConfigError(Exception):
    """The settings file cannot be used; the text says why."""


@dataclass(frozen=True)
class Config:
    language: str | None = None
    order: tuple[str, ...] = ()
    hide: frozenset[str] = frozenset()
    rename: dict[str, str] = field(default_factory=dict)
    tiles: tuple[Tile, ...] = ()


def check_keys(table: dict, allowed: set[str]) -> None:
    unknown = table.keys() - allowed
    if unknown:
        raise ConfigError(f'unknown setting "{min(unknown)}"')


def text(table: dict, key: str) -> str:
    value = table.get(key, "")
    if not isinstance(value, str):
        raise ConfigError(f'"{key}" must be a string')
    return value


def texts(table: dict, key: str) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f'"{key}" must be a list of strings')
    return value


def language(table: dict) -> str | None:
    value = text(table, "language")
    if value and value not in AVAILABLE:
        raise ConfigError(f'"language" must be one of {", ".join(sorted(AVAILABLE))}, not "{value}"')
    return value or None


def rename(table: dict) -> dict[str, str]:
    value = table.get("rename", {})
    if not isinstance(value, dict) or not all(isinstance(title, str) for title in value.values()):
        raise ConfigError('"rename" must be a table of strings')
    return value


def custom_tile(table: dict) -> Tile:
    check_keys(table, {"id", "name", "icon", "command"})
    name, command = text(table, "name"), text(table, "command")
    for key, value in (("name", name), ("command", command)):
        if not value.strip():
            raise ConfigError(f'a tile needs "{key}"')
    tile_id = text(table, "id") or re.sub(r"\W+", "-", name.casefold()).strip("-")
    if not tile_id or tile_id in RESERVED_IDS:
        raise ConfigError(f'a tile cannot have the id "{tile_id}"')
    try:
        argv = shlex.split(command)
    except ValueError as error:
        raise ConfigError(f'"command" of "{name}": {error}') from error
    # The words that were quoted or escaped, by the POSIX rules that shlex.split follows as well: a link there
    # would become part of the text the quotes protect, such as a shell script.
    quoted = [word for word, marked in split_marked(command, lambda char: char in SHLEX_BLANKS) if marked]
    if takes_url(tuple(quoted)):
        raise ConfigError(f'"command" of "{name}": {LINK_IN_QUOTES}')
    return Tile(tile_id, name, text(table, "icon"), tuple(argv if takes_url(tuple(argv)) else [*argv, "%U"]))


def custom_tiles(table: dict) -> tuple[Tile, ...]:
    tables = table.get("tile", [])
    if not isinstance(tables, list) or not all(isinstance(item, dict) for item in tables):
        raise ConfigError('"tile" must be [[tile]] tables')
    tiles = [custom_tile(item) for item in tables]
    for position, tile in enumerate(tiles):
        if tile.id in {other.id for other in tiles[:position]}:
            raise ConfigError(f'two tiles have the id "{tile.id}"')
    return tuple(tiles)


def load(path: Path) -> Config:
    try:
        table = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return Config()
    except (OSError, ValueError, RecursionError) as error:
        raise ConfigError(str(error)) from error
    check_keys(table, {"language", "order", "hide", "rename", "tile"})
    return Config(language(table), tuple(texts(table, "order")), frozenset(texts(table, "hide")), rename(table),
                  custom_tiles(table))
