#!/bin/bash
# focus.sh checks with real input events that the chosen browser, already running, comes to the front.
# It needs Plasma 6, libei and python3-gi. It does not touch the user's session.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d /tmp/kbc.XXXXXX)
trap 'rm -rf "$work"' EXIT
python3 "$here/../../tools/build.py" --out "$work/dist" 2>/dev/null
python3 "$here/strip_token.py" "$work/dist/kde-browser-chooser" "$work/dist/stripped"
chmod +x "$work/dist/stripped"

mkdir -p "$work"/{bin,data/applications,config/kde-browser-chooser,state/kde-browser-chooser}
# shellcheck disable=SC2016 # expands in the fake browser
printf '#!/bin/sh\nprintf "%%s\\n" "$XDG_ACTIVATION_TOKEN" >"%s"\n' "$work/fifo" >"$work/bin/fake-browser"
printf '[Desktop Entry]\nType=Application\nName=Fake\nExec=%s %%u\nMimeType=x-scheme-handler/https;\n' \
	"$work/bin/fake-browser" >"$work/data/applications/fakebrowser.desktop"
# Only the fake browser and "Cancel", so that the tiles are where scenario.sh clicks.
hidden=$(XDG_DATA_HOME="$work/data" XDG_CONFIG_HOME="$work/config" "$work/dist/kde-browser-chooser" --list |
	cut -f1 | grep -v '^fakebrowser$' | sed 's/.*/"&",/' | tr -d '\n')
echo "hide = [$hidden]" >"$work/config/kde-browser-chooser/config.toml"
echo fakebrowser >"$work/state/kde-browser-chooser/last"

run() { # run NAME WANT SCENARIO PROGRAM...
	local name=$1 want=$2 scenario=$3
	shift 3
	printf '#!/bin/sh\nexec %s "$@"\n' "$*" >"$work/bin/xdg-open"
	chmod +x "$work/bin"/*
	rm -f "$work/result"
	"$here/nested.sh" "$work" 1 "$here/scenario.sh" "$work" "$scenario" || true
	local got
	got=$(cat "$work/result" 2>/dev/null || echo "no answer")
	echo "$name: $got"
	[ "$got" = "$want" ] || failed=1
}

failed=0
run "control (no chooser)" True control "$work/bin/fake-browser"
run "click" True click "$work/dist/kde-browser-chooser" --
run "enter" True enter "$work/dist/kde-browser-chooser" --
run "click without a fresh token" False click "$work/dist/stripped" --
exit $failed
