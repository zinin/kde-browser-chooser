"""A plain kdialog list, for when PyQt6 cannot show the window."""
import html
import subprocess
from collections.abc import Mapping

from .model import Tile
from .window import ICON


def pick_with_kdialog(tiles: list[Tile], label: str, counter: str, last: str,
                      strings: Mapping[str, str]) -> Tile | None:
    by_id = {tile.id: tile for tile in tiles}
    after = f" {counter}" if counter else ""  # the counter of links stays whole: only the link is cut
    room = 110 - len(after)
    shown = (label if len(label) <= room else label[:room - 3] + "...") + after
    menu = [word for tile in tiles for word in (tile.id, tile.title)]
    default = ["--default", by_id[last].title] if last in by_id else []  # kdialog wants the title
    # As rich text the label shows < > & as such; after "--" no item that starts with "-" is an option.
    result = subprocess.run(
        ["kdialog", "--title", strings["title"], "--icon", ICON, *default,
         "--menu", "<qt>" + html.escape(shown, quote=False) + "</qt>", "--", *menu],
        stdout=subprocess.PIPE, text=True)
    if result.returncode == 1:  # "Cancel"
        return None
    if result.returncode != 0:
        raise RuntimeError(f"kdialog exited with {result.returncode}")
    answer = result.stdout.removesuffix("\n")
    if answer not in by_id:  # an answer that is no tile must not drop the link silently
        raise RuntimeError(f"kdialog answered {answer!r}")
    return by_id[answer]
