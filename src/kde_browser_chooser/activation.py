"""Asks KWin for an xdg-activation token, so that the browser may come to the front.

The token this program was started with is outdated by the click on a tile:
with it KWin leaves a browser that is already running behind other windows.
"""
import ctypes
import os
from collections.abc import Callable

from .log import log_exception

TOKEN_WAIT_MS = 300


def kwayland_extras():
    """KWaylandExtras of KDE Frameworks, which have no Python bindings; None unless on Wayland.

    Its methods are called through the Qt meta-object. requestXdgActivationToken()
    takes a uint32_t, which PyQt can pass only because QtWayland registers that
    name; without it, or without the library, the call raises and the link opens
    with the old token.
    """
    from PyQt6 import sip
    from PyQt6.QtCore import QObject
    from PyQt6.QtGui import QGuiApplication

    if not QGuiApplication.platformName().startswith("wayland"):
        return None
    instance = ctypes.CDLL("libKF6WindowSystem.so.6")._ZN14KWaylandExtras4selfEv  # KWaylandExtras::self()
    instance.restype = ctypes.c_void_p
    return sip.wrapinstance(instance(), QObject)


def request_token(window, done: Callable[[], object]) -> None:
    """Puts a new token into the environment, then calls done(), in any case and soon."""
    from PyQt6.QtCore import QTimer

    def arrived(_serial: int, token: str) -> None:
        try:
            if token:
                os.environ["XDG_ACTIVATION_TOKEN"] = token
            done()
        except Exception:  # out of a Qt slot it would abort the process, and the link would be lost
            log_exception()

    try:
        extras = kwayland_extras()
        if extras is None:
            done()
            return
        extras.xdgActivationTokenArrived.connect(arrived)
        handle = window.windowHandle()
        extras.requestXdgActivationToken(handle, extras.lastInputSerial(handle), "")
        QTimer.singleShot(TOKEN_WAIT_MS, done)
    except Exception:  # out of a Qt slot it would abort the process, and the link would be lost
        log_exception()
        done()
