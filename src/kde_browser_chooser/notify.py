import contextlib
import sys

from . import dbus
from .process import succeeds

APP = "Browser Chooser"


def notify(icon: str, summary: str, body: str) -> None:
    """Shows a notification by any means there are; never raises."""
    summary, body = summary.replace("\0", ""), body.replace("\0", "")  # no argument can hold a null byte
    shown = succeeds(["notify-send", "-a", APP, "-h", "string:desktop-entry:kde-browser-chooser",
                      "-i", icon, "--", summary, body]) or dbus.call(
        "org.freedesktop.Notifications", "/org/freedesktop/Notifications", "org.freedesktop.Notifications", "Notify",
        ("s", APP), ("u", "0"), ("s", icon), ("s", summary), ("s", body), ("as", ""), ("a{sv}", ""), ("i", "10000"))
    if not shown:
        with contextlib.suppress(Exception):
            print(f"{summary}: {body}", file=sys.stderr)
