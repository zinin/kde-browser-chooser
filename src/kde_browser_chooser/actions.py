"""What the tiles do: copy the link or become the browser."""
import contextlib
import os
import re
import signal
import subprocess
from collections.abc import Mapping

from . import dbus
from .model import Tile
from .notify import notify
from .process import succeeds


def expand(command: tuple[str, ...], urls: list[str]) -> list[list[str]]:
    """One argv for all links (%U, %F) or one per link (%u, %f)."""
    per_link = any(re.search("%[uf]", word.replace("%%", "")) for word in command)
    return [expand_for(command, links) for links in (([[url] for url in urls] or [[]]) if per_link else [urls])]


def expand_for(command: tuple[str, ...], urls: list[str]) -> list[str]:
    argv: list[str] = []
    for word in command:
        if re.fullmatch("%[uUfF]", word):
            argv += urls
        else:
            argv.append(re.sub("%[%uUfF]", lambda code: "%" if code[0] == "%%" else " ".join(urls), word))
    return argv


def become(argv: list[str]) -> None:
    """Replaces this process with the browser, leaving it no traces of Python and Qt."""
    # Python ignores these signals, and the browser would inherit that.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    # Qt keeps the graphics card (/dev/dri/renderD*) open without O_CLOEXEC.
    for fd in map(int, os.listdir("/proc/self/fd")):
        if fd > 2:
            with contextlib.suppress(OSError):  # the descriptor of listdir itself is gone
                os.set_inheritable(fd, False)
    # os.environ on purpose: Qt removes XDG_ACTIVATION_TOKEN from the process
    # environment once it shows a window, and without a token the browser
    # would stay behind other windows.
    os.execvpe(argv[0], argv, os.environ)


def launch(tile: Tile, urls: list[str], strings: Mapping[str, str]) -> int:
    """Does not return when the browser starts."""
    *others, last = expand(tile.command, urls)
    try:
        for argv in others:
            subprocess.Popen(argv, start_new_session=True)
        become(last)
    except OSError as error:
        notify("dialog-error", strings["launch_failed"].format(name=tile.title), f"{error.strerror}: {last[0]}")
    return 1


def copy(urls: list[str], strings: Mapping[str, str]) -> int:
    text = "\n".join(urls)
    # wl-copy first: Klipper also overwrites the selection that a middle click pastes.
    copied = (bool(os.environ.get("WAYLAND_DISPLAY")) and succeeds(["wl-copy"], os.fsencode(text))) or dbus.call(
        "org.kde.klipper", "/klipper", "org.kde.klipper.klipper", "setClipboardContents", ("s", text))
    notify("edit-copy" if copied else "dialog-error", strings["copied" if copied else "copy_failed"], text)
    return 0 if copied else 1
