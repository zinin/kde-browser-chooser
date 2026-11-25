#!/bin/sh
# Runs inside a container as root: installs the program for an ordinary user and checks that it works.
set -eu

if command -v apt-get >/dev/null; then
	apt-get update -qq
	DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sudo curl python3 >/dev/null
elif command -v dnf >/dev/null; then
	dnf install -y -q sudo curl python3 >/dev/null
elif command -v pacman >/dev/null; then
	pacman -Sy --noconfirm --needed sudo curl python >/dev/null
elif command -v zypper >/dev/null; then
	zypper --quiet --non-interactive refresh
	zypper --quiet --non-interactive install sudo curl python3 gawk coreutils >/dev/null
fi
useradd -m tester
echo 'tester ALL=(ALL) NOPASSWD: ALL' >/etc/sudoers.d/tester

cat >/tmp/as-user.sh <<'USER'
set -eu
export XDG_CURRENT_DESKTOP=KDE KBC_BASE_URL=file:///dist QT_QPA_PLATFORM=offscreen
cat /src/install.sh | sh -s -- --yes
/usr/bin/python3 -I -c 'import PyQt6.QtWidgets'
program=$HOME/.local/bin/kde-browser-chooser
"$program" --list | grep -q '^copy'
# The window lives for 3 seconds; timeout ends it with 124.
status=0
timeout 3 "$program" -- https://example.com/ 2>/tmp/stderr || status=$?
cat /tmp/stderr
[ "$status" = 124 ]
! grep -q Traceback /tmp/stderr
cat /src/install.sh | sh -s -- --uninstall
[ ! -e "$program" ] && [ ! -e "$HOME/.local/share/applications/kde-browser-chooser.desktop" ]
USER
sudo -H -u tester sh /tmp/as-user.sh
