"""inject.py X Y | inject.py key CODE makes a real click or key press in the nested KWin, through its own EIS."""
import ctypes as C
import select
import sys
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

POINTER_ABSOLUTE, KEYBOARD, BUTTON = 2, 4, 32
SEAT_ADDED, DEVICE_RESUMED, DISCONNECTED = 3, 8, 2
LEFT_BUTTON = 0x110
key = int(sys.argv[2]) if sys.argv[1] == "key" else None
x, y = (0, 0) if key else map(float, sys.argv[1:])

bus = Gio.bus_get_sync(Gio.BusType.SESSION)
_, fds = bus.call_with_unix_fd_list_sync(
    "org.kde.KWin", "/org/kde/KWin/EIS/RemoteDesktop", "org.kde.KWin.EIS.RemoteDesktop", "connectToEIS",
    GLib.Variant("(i)", (7,)), None, Gio.DBusCallFlags.NONE, 5000, None, None)
fd = fds.get(0)
lib = C.CDLL("libei.so.1")
P = C.c_void_p


def function(name, result, *args):
    f = getattr(lib, name)
    f.restype, f.argtypes = result, args
    return f


dispatch = function("ei_dispatch", None, P)
get_event = function("ei_get_event", P, P)
event_type = function("ei_event_get_type", C.c_int, P)
event_seat = function("ei_event_get_seat", P, P)
event_device = function("ei_event_get_device", P, P)
unref = function("ei_event_unref", P, P)
has = function("ei_device_has_capability", C.c_bool, P, C.c_int)
frame = function("ei_device_frame", None, P, C.c_uint64)
now = function("ei_now", C.c_uint64, P)
get_fd = function("ei_get_fd", C.c_int, P)
motion = function("ei_device_pointer_motion_absolute", None, P, C.c_double, C.c_double)
button = function("ei_device_button_button", None, P, C.c_uint32, C.c_bool)
keyboard = function("ei_device_keyboard_key", None, P, C.c_uint32, C.c_bool)

context = function("ei_new_sender", P, P)(None)
if function("ei_setup_backend_fd", C.c_int, P, C.c_int)(context, fd):
    sys.exit("EIS: cannot connect")
device, deadline = None, time.time() + 4
while device is None and time.time() < deadline:
    select.select([get_fd(context)], [], [], 0.2)
    dispatch(context)
    while event := get_event(context):
        kind = event_type(event)
        if kind == SEAT_ADDED:
            lib.ei_seat_bind_capabilities(P(event_seat(event)), C.c_int(POINTER_ABSOLUTE), C.c_int(BUTTON),
                                          C.c_int(KEYBOARD), P(None))
        elif kind == DEVICE_RESUMED:
            found = event_device(event)
            if has(found, KEYBOARD) if key else has(found, POINTER_ABSOLUTE) and has(found, BUTTON):
                device = found
        elif kind == DISCONNECTED:
            sys.exit("EIS: disconnected")
        if device is None:
            unref(event)
if device is None:
    sys.exit("EIS: no device")
function("ei_device_start_emulating", None, P, C.c_uint32)(device, 1)


def send(step, *args):
    step(device, *args)
    frame(device, now(context))
    dispatch(context)
    time.sleep(0.12)


if key:
    send(keyboard, key, True)
    send(keyboard, key, False)
else:
    send(motion, x, y)
    send(button, LEFT_BUTTON, True)
    send(button, LEFT_BUTTON, False)
