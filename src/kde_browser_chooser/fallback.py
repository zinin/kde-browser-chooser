"""A plain kdialog list, for when PyQt6 cannot show the window."""
import html
import subprocess
from collections.abc import Mapping

from .model import Tile
from .window import ICON


def pick_with_kdialog(tiles: list[Tile], label: str, last: str, strings: Mapping[str, str]) -> Tile | None:
    by_id = {tile.id: tile for tile in tiles}
    shown = label if len(label) <= 110 else label[:107] + "..."
    menu = [word for tile in tiles for word in (tile.id, tile.title)]
    default = ["--default", by_id[last].title] if last in by_id else []  # kdialog wants the title
    result = subprocess.run(
        ["kdialog", "--title", strings["title"], "--icon", ICON, *default,
         "--menu", html.escape(shown, quote=False), *menu],
        stdout=subprocess.PIPE, text=True)
    if result.returncode not in (0, 1):  # 1 is "Cancel"
        raise RuntimeError(f"kdialog exited with {result.returncode}")
    return by_id.get(result.stdout.strip()) if result.returncode == 0 else None
