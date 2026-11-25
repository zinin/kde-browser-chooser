#!/bin/bash
# nested.sh WORK SCALE COMMAND... runs COMMAND in a KWin of its own, without a screen.
# WORK is a directory for its settings and sockets; keep its path short.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$1 scale=$2
shift 2
mkdir -p "$work"/{run,config,cache,data,state}
chmod 700 "$work/run"
cp ~/.config/kdeglobals "$work/config/" 2>/dev/null || true

session() {
	printf '#!/bin/bash\n%s\n' "$(printf '%q ' "$@")" >"$work/session.sh"
	chmod +x "$work/session.sh"
	# XDG_RUNTIME_DIR too: without WAYLAND_DISPLAY libwayland would take the user's own wayland-0 from it.
	env -u DISPLAY -u WAYLAND_DISPLAY -u XDG_ACTIVATION_TOKEN -u DESKTOP_STARTUP_ID \
		XDG_RUNTIME_DIR="$work/run" XDG_CONFIG_HOME="$work/config" XDG_CACHE_HOME="$work/cache" \
		XDG_DATA_HOME="$work/data" XDG_STATE_HOME="$work/state" KWIN_SCREENSHOT_NO_PERMISSION_CHECKS=1 \
		timeout 40 prlimit --core=1:1 dbus-run-session --config-file="$here/bus.conf" -- \
		kwin_wayland --virtual --width 2880 --height 1800 --no-lockscreen --no-global-shortcuts \
		--socket wayland-kbc --exit-with-session "$work/session.sh" 2>"$work/kwin.log"
}

outputs=$work/config/kwinoutputconfig.json
if [ "$scale" != 1 ] && [ ! -e "$outputs" ]; then
	session sleep 1 # KWin writes the file the scale is set in
fi
if [ -e "$outputs" ]; then
	sed -i -E "s/\"scale\": [0-9.]+/\"scale\": $scale/" "$outputs"
fi
session "$@"
