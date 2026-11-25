"""capture.py OUT.png METHOD takes a screenshot of the nested KWin, for example with CaptureActiveWindow."""
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
from PyQt6.QtGui import QImage

out, method = sys.argv[1:]
bus = Gio.bus_get_sync(Gio.BusType.SESSION)
read_end, write_end = os.pipe()
fds = Gio.UnixFDList.new()
index = fds.append(write_end)
os.close(write_end)
options = {"include-decoration": GLib.Variant("b", True), "native-resolution": GLib.Variant("b", True)}
reply, _ = bus.call_with_unix_fd_list_sync(
    "org.kde.KWin", "/org/kde/KWin/ScreenShot2", "org.kde.KWin.ScreenShot2", method,
    GLib.Variant("(a{sv}h)", (options, index)), GLib.VariantType("(a{sv})"), Gio.DBusCallFlags.NONE, 5000, fds, None)
meta = reply.unpack()[0]
del fds
data = b""
while len(data) < meta["stride"] * meta["height"] and (chunk := os.read(read_end, 1 << 20)):
    data += chunk
image = QImage(data, meta["width"], meta["height"], meta["stride"], QImage.Format(meta["format"]))
sys.exit(not image.save(out))
