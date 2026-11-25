# Nested KWin bench

`focus.sh` checks what the unit tests cannot: that the browser chosen in the window comes to the
front. It starts a KWin without a screen, with a running fake browser and, in front of it, a program
with a link; it clicks the link and a tile with real input events, sent through KWin's EIS, and asks
the browser whether it became active. The last line must be `False`: there the program is stripped
of its request for a fresh token, so the bench is able to notice a failure.

It needs Plasma 6, libei, python3-gi and PyQt6, and runs on the developer's machine, not in CI.

Two traps, both already avoided in `nested.sh`:

- With D-Bus activation the nested session starts xdg-desktop-portal and ksecretd, which crash there
  by the hundred, and systemd-coredump of the host keeps every core. Hence `bus.conf` without
  `servicedirs` and `prlimit --core=1:1`.
- Unsetting `WAYLAND_DISPLAY` does not isolate anything: libwayland then connects to `wayland-0` in
  `XDG_RUNTIME_DIR`, that is, to the user's own desktop. Hence `XDG_RUNTIME_DIR` is replaced too.

`capture.py` takes a screenshot of the nested session; `nested.sh WORK SCALE COMMAND...` runs
anything in it.
