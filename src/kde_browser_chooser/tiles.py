from collections.abc import Mapping
from dataclasses import replace

from .config import Config
from .model import Tile


def build(browsers: list[Tile], config: Config, strings: Mapping[str, str], has_link: bool) -> list[Tile]:
    """Orders all tiles but "Cancel", which the window adds itself."""
    copy = [Tile("copy", strings["copy"], "edit-copy", None)] if has_link else []
    tiles = {tile.id: tile for tile in [*copy, *browsers, *config.tiles]}
    ordered = dict.fromkeys(tile_id for tile_id in [*config.order, *tiles] if tile_id in tiles)
    return [replace(tiles[tile_id], title=config.rename.get(tile_id, tiles[tile_id].title))
            for tile_id in ordered if tile_id not in config.hide]
