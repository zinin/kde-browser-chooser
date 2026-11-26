"""Remembers the last choice."""
import contextlib
from pathlib import Path

from .model import Tile


def read_last(path: Path, tiles: list[Tile]) -> str:
    last = ""
    with contextlib.suppress(OSError, UnicodeDecodeError):
        last = path.read_text(encoding="utf-8").removesuffix("\n")  # what save_last wrote: an id may end in a space
    ids = [tile.id for tile in tiles]
    return last if last in ids else next(iter(ids), "")


def save_last(path: Path, tile_id: str) -> None:
    with contextlib.suppress(OSError, ValueError):  # a choice not remembered is no reason not to open the link
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{tile_id}\n", encoding="utf-8")
