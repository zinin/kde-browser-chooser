from dataclasses import dataclass


@dataclass(frozen=True)
class Tile:
    """One tile of the window; "Cancel" is not a Tile."""

    id: str
    title: str
    icon: str  # icon theme name or absolute path
    command: tuple[str, ...] | None  # argv with %% and URL field codes; None copies the link
