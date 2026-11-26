#!/bin/sh
# Runs inside a container as root: installs the program for ordinary users, with the real xdg-utils,
# and checks that it works, becomes the default browser and gives everything back.
set -eu

if command -v apt-get >/dev/null; then
	apt-get update -qq
	DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
		sudo curl ca-certificates python3 xdg-utils desktop-file-utils libkf6config-bin >/dev/null
elif command -v dnf >/dev/null; then
	dnf install -y -q sudo curl python3 xdg-utils desktop-file-utils kf6-kconfig >/dev/null
elif command -v pacman >/dev/null; then
	pacman -Sy --noconfirm --needed sudo curl python xdg-utils desktop-file-utils kconfig >/dev/null
elif command -v zypper >/dev/null; then
	zypper --quiet --non-interactive refresh
	zypper --quiet --non-interactive install sudo curl python3 gawk coreutils xdg-utils desktop-file-utils kf6-kconfig >/dev/null
fi
command -v kwriteconfig6 >/dev/null || echo "note: no kwriteconfig6 in this image"

mkdir -p /usr/share/applications
cat >/usr/share/applications/fakebrowser.desktop <<'ENTRY'
[Desktop Entry]
Type=Application
Name=Fake
Exec=/bin/true %U
MimeType=x-scheme-handler/http;x-scheme-handler/https;text/html;application/xhtml+xml;
ENTRY
update-desktop-database /usr/share/applications

cat >/tmp/as-user.sh <<'USER'
set -eu
export XDG_CURRENT_DESKTOP=KDE KDE_SESSION_VERSION=6 KBC_BASE_URL=file:///dist QT_QPA_PLATFORM=offscreen
ours=kde-browser-chooser.desktop
program=$HOME/.local/bin/kde-browser-chooser
types='x-scheme-handler/http x-scheme-handler/https text/html application/xhtml+xml'

# What the user has chosen; the associations that xdg-utils add on the way do not count.
settings() {
	for file in mimeapps.list kdeglobals; do
		if [ -e "$HOME/.config/$file" ]; then
			awk '/^\[/ { group = $0 } /=/ && group != "[Added Associations]" { print group, $0 }' "$HOME/.config/$file"
		fi
	done | sort
}

# What opens each type now, chosen or not.
effective() {
	for type in $types; do
		echo "$type=$(xdg-mime query default "$type" 2>/dev/null)"
	done
}

run_installer() {
	sh -s -- "$@" </src/install.sh
}

check_default() {
	for type in $types; do
		[ "$(xdg-mime query default "$type" 2>/dev/null)" = "$ours" ] || { echo "not the default for $type"; exit 1; }
		settings | grep -qF "$type=$ours" || { echo "not chosen for $type"; exit 1; }
	done
	if command -v kwriteconfig6 >/dev/null; then
		settings | grep -qF "BrowserApplication=$ours" || { echo "not in kdeglobals"; exit 1; }
	fi
}

check_removed() {
	[ ! -e "$program" ]
	if grep -rs kde-browser-chooser "$HOME/.config" "$HOME/.local/share/applications"; then
		echo "traces are left"
		exit 1
	fi
}

echo "== $HOME: no browser chosen"
run_installer --yes
/usr/bin/python3 -I -c 'import PyQt6.QtWidgets'
check_default
"$program" --list | grep -q '^fakebrowser'
# The window lives for 3 seconds; timeout ends it with 124.
status=0
timeout 3 "$program" -- https://example.com/ 2>"$HOME/stderr" || status=$?
cat "$HOME/stderr"
[ "$status" = 124 ]
if grep -q Traceback "$HOME/stderr"; then exit 1; fi
run_installer --uninstall
check_removed
[ "$(xdg-mime query default x-scheme-handler/https 2>/dev/null)" = fakebrowser.desktop ]

echo "== $HOME: not the default"
# Our entry could take over a type that nobody chose just by being there.
before=$(effective)
run_installer --no-default
"$program" --version >/dev/null
if [ "$(effective)" != "$before" ]; then
	printf 'before:\n%s\nafter:\n%s\n' "$before" "$(effective)"
	exit 1
fi
run_installer --uninstall
check_removed
[ "$(effective)" = "$before" ]

echo "== $HOME: a browser chosen"
xdg-settings set default-web-browser fakebrowser.desktop 2>/dev/null
xdg-mime default fakebrowser.desktop application/xhtml+xml 2>/dev/null
before=$(settings)
run_installer --yes
check_default
run_installer --yes
run_installer --uninstall
check_removed
if [ "$(settings)" != "$before" ]; then
	printf 'before:\n%s\nafter:\n%s\n' "$before" "$(settings)"
	exit 1
fi
USER

number=0
for home in /home/tester '/home/a b' /home/user@corp.example; do
	number=$((number + 1))
	useradd -m -d "$home" "tester$number"
	echo "tester$number ALL=(ALL) NOPASSWD: ALL" >"/etc/sudoers.d/tester$number"
	sudo -H -u "tester$number" sh /tmp/as-user.sh
done
