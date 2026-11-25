#!/bin/sh
# install.sh installs kde-browser-chooser for the current user from its GitHub releases:
#
#   curl -fsSL https://raw.githubusercontent.com/zinin/kde-browser-chooser/master/install.sh | sh
#
# It checks the download against the release's SHA256SUMS, puts the program into
# ~/.local/bin and offers to install PyQt6 and to make the program the default
# browser. Run it again to update. "| sh -s -- --uninstall" removes the program
# and brings back the previous default browser. KBC_VERSION picks another release,
# such as 0.1.0, and KBC_INSTALL_DIR another directory for the program.
set -eu

repo=zinin/kde-browser-chooser
app=kde-browser-chooser
ours=$app.desktop
keys='x-scheme-handler/http x-scheme-handler/https text/html application/xhtml+xml kdeglobals'
by_hand='System Settings, Default Applications, Web browser'

say() {
	echo "$app: $*"
}

fail() {
	echo "$app: $*" >&2
	exit 1
}

usage() {
	cat <<USAGE
Usage: install.sh [--yes] [--no-default] [--version X]
       install.sh --uninstall [--purge]

  --yes         take the suggested answer to every question
  --no-default  do not offer to make the program the default browser
  --version X   install the release X instead of the latest
  --uninstall   remove the program and bring back the previous default browser
  --purge       with --uninstall: remove the settings too
USAGE
}

has() {
	command -v "$1" >/dev/null 2>&1
}

# ask puts the question $1; the letter $2, y or n, is the answer of Enter and of --yes.
ask() {
	if [ "$yes" = 1 ]; then
		[ "$2" = y ]
		return
	fi
	if [ "$tty" = 0 ]; then
		say "$1 There is no terminal to ask on, so no; --yes takes the suggested answers."
		return 1
	fi
	if [ "$2" = y ]; then hint='[Y/n]'; else hint='[y/N]'; fi
	printf '%s: %s %s ' "$app" "$1" "$hint"
	read -r answer <&3 || answer=n # Ctrl+D
	case ${answer:-$2} in
	[Yy]*) return 0 ;;
	*) return 1 ;;
	esac
}

# fetch downloads the URL $1 into the file $2.
fetch() {
	if has curl; then
		curl -fsSL -o "$2" "$1"
	elif has wget; then
		wget -q -O "$2" "$1"
	else
		fail "neither curl nor wget is installed"
	fi
}

check_system() {
	[ "$(uname -s)" = Linux ] || fail "it runs only on Linux"
	[ "$(id -u)" -ne 0 ] || fail "run it as the user who clicks the links, not as root"
	[ -n "${HOME:-}" ] || fail "HOME is not set"
}

check_desktop() {
	case ${XDG_CURRENT_DESKTOP:-} in
	*KDE*) return ;;
	esac
	if has plasmashell; then return; fi
	say "this does not look like KDE Plasma, the only desktop it is made for."
	ask "Install it anyway?" n || fail "nothing is installed"
}

check_python() {
	"$python" -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null ||
		fail "it needs Python 3.11 or later as /usr/bin/python3"
}

has_pyqt() {
	"$python" -I -c 'import PyQt6.QtWidgets' 2>/dev/null
}

ensure_pyqt() {
	if has_pyqt; then return; fi
	if [ -e "${KBC_SYSROOT:-}/run/ostree-booted" ]; then
		say "PyQt6 is missing; add it with: rpm-ostree install python3-pyqt6"
		return
	fi
	if has apt-get; then
		install='apt-get install -y python3-pyqt6'
	elif has dnf; then
		install='dnf install -y python3-pyqt6'
	elif has pacman; then
		install='pacman -S --needed --noconfirm python-pyqt6'
	elif has zypper; then
		install='zypper --non-interactive install python3-PyQt6'
	else
		say "PyQt6 is missing; install it for /usr/bin/python3 with your package manager."
		return
	fi
	if ! has sudo; then
		say "PyQt6 is missing; install it as root: $install"
		return
	fi
	say "PyQt6, which draws the window, is missing."
	if ask "Run \"sudo $install\"?" y; then
		# shellcheck disable=SC2086 # a command and its arguments
		sudo $install </dev/null || true
	fi
	has_pyqt || say "there is still no PyQt6, so there will be no window."
}

download() {
	if [ -n "${KBC_BASE_URL:-}" ]; then
		base=$KBC_BASE_URL
	elif [ -n "$version" ]; then
		base="https://github.com/$repo/releases/download/v${version#v}"
	else
		base="https://github.com/$repo/releases/latest/download"
	fi
	for file in SHA256SUMS "$app" "$ours"; do
		fetch "$base/$file" "$tmp/$file" || fail "cannot download $base/$file"
	done
	for file in "$app" "$ours"; do
		want=$(awk -v name="$file" '$2 == name { print $1 }' "$tmp/SHA256SUMS")
		got=$(sha256sum "$tmp/$file" | awk '{ print $1 }')
		if [ -z "$want" ] || [ "$got" != "$want" ]; then
			fail "$file does not match its SHA256SUMS"
		fi
	done
}

# exec_value prints the path $1 as Exec wants it, quoted if the Desktop Entry Specification reserves
# one of its characters. xdg-utils do not understand a quoted program, but they do understand env.
# \ " ` $ are escaped twice, in the quoted argument and in the string: one \ in the path becomes four.
exec_value() {
	reserved=$(printf '%s' "$1" | LC_ALL=C tr -d 'A-Za-z0-9/._+@:,=\200-\377-')
	if [ -z "$reserved" ]; then
		printf '%s' "$1"
	else
		printf '/usr/bin/env "%s"' "$(printf '%s' "$1" | sed -e 's/\\/\\\\\\\\/g' -e 's/["`$]/\\\\&/g' -e 's/%/%%/g')"
	fi
}

refresh() {
	if has update-desktop-database; then update-desktop-database "$apps_dir" >/dev/null 2>&1 || true; fi
	if has kbuildsycoca6; then kbuildsycoca6 >/dev/null 2>&1 || true; fi
}

place() {
	mkdir -p "$bin_dir" "$apps_dir"
	new=${bin_dir:?}/.${app:?}.new
	cp "$tmp/$app" "$new"
	chmod 755 "$new"
	if ! installed=$("$new" --version); then
		rm -f "${new:?}"
		fail "the program does not run on this system"
	fi
	mv -f "$new" "$bin_dir/$app"
	EXEC=$(exec_value "$bin_dir/$app") awk '
		{ at = index($0, "@EXEC@") }
		at { $0 = substr($0, 1, at - 1) ENVIRON["EXEC"] substr($0, at + 6) }
		{ print }' "$tmp/$ours" >"$apps_dir/.$ours.new"
	mv -f "$apps_dir/.$ours.new" "$apps_dir/$ours"
	refresh
	say "$installed is in $bin_dir"
	case ":$PATH:" in
	*":$bin_dir:"*) ;;
	*) say "$bin_dir is not on your PATH; links open anyway." ;;
	esac
}

# setting prints the value of the key $3 in the group $2 of the file $1.
setting() {
	if [ -e "$1" ]; then
		awk -v group="$2" -v key="$3=" '
			/^\[/ { inside = ($0 == group) }
			inside && index($0, key) == 1 { print substr($0, length(key) + 1); exit }' "$1"
	fi
}

# chosen prints what the user has chosen for the key $1. The effective default would not do: our entry
# can become that just by being there.
chosen() {
	case $1 in
	kdeglobals) setting "$config_home/kdeglobals" '[General]' BrowserApplication ;;
	*) setting "$mimeapps" '[Default Applications]' "$1" ;;
	esac
}

is_ours() {
	case $1 in
	"$ours" | "$ours;"*) return 0 ;;
	*) return 1 ;;
	esac
}

is_chosen() {
	is_ours "$(chosen x-scheme-handler/http)" && is_ours "$(chosen x-scheme-handler/https)"
}

# recorded prints what was chosen for the key $1 before us.
recorded() {
	if [ -e "$state_dir/previous-defaults" ]; then
		awk -v key="$1=" 'index($0, key) == 1 { print substr($0, length(key) + 1) }' "$state_dir/previous-defaults"
	fi
}

save_previous() {
	mkdir -p "$state_dir"
	for key in $keys; do
		value=$(chosen "$key")
		if is_ours "$value"; then value=$(recorded "$key"); fi
		if [ -n "$value" ]; then echo "$key=$value"; fi
	done >"$state_dir/previous-defaults.new"
	mv -f "$state_dir/previous-defaults.new" "$state_dir/previous-defaults"
}

make_default() {
	if ! has xdg-settings; then
		say "there is no xdg-settings; make it the default browser in $by_hand."
		return
	fi
	if is_chosen; then return; fi
	suggested=y
	if ! has_pyqt; then
		if ! has kdialog; then
			say "it cannot be the default browser without PyQt6 or kdialog: it would have nothing to show."
			return
		fi
		say "without PyQt6 it shows a plain list, and a running browser may stay behind other windows."
		suggested=n
	fi
	ask "Make it the default browser?" "$suggested" || return 0
	save_previous
	mkdir -p "$config_home" # xdg-mime would lose its first change without it
	xdg-settings set default-web-browser "$ours" >/dev/null 2>&1 || true
	if is_chosen; then
		xdg-mime default "$ours" application/xhtml+xml >/dev/null 2>&1 || true
	else
		say "that had no effect; make it the default browser in $by_hand."
		return 0
	fi
	# xdg-settings stops at the first type it cannot set, so every key is checked.
	others=
	for key in $keys; do
		is_ours "$(chosen "$key")" || others="$others $key"
	done
	if [ -z "$others" ]; then
		say "it is the default browser now; programs already running may need a restart."
	else
		say "links open through it now, but$others still belong to other programs; make it the default browser in $by_hand."
	fi
}

# note_effective writes down, for each type of our entry that the user has not chosen, the program that
# opens it now: our entry can take its place just by being there.
note_effective() {
	: >"$tmp/effective"
	if ! has xdg-mime; then return; fi
	for key in $keys; do
		if [ "$key" = kdeglobals ] || [ -n "$(chosen "$key")" ]; then continue; fi
		value=$(xdg-mime query default "$key" </dev/null 2>/dev/null) || value=
		if [ -n "$value" ] && ! is_ours "$value"; then echo "$key=$value"; fi
	done >"$tmp/effective"
}

# keep_effective makes the noted programs the user's choice where our entry has taken their place, so that
# not becoming the default browser changes nothing.
keep_effective() {
	while IFS= read -r line; do
		key=${line%%=*}
		if [ -z "$(chosen "$key")" ] && is_ours "$(xdg-mime query default "$key" </dev/null 2>/dev/null)"; then
			echo "$line"
		fi
	done <"$tmp/effective" >"$tmp/kept"
	if [ ! -s "$tmp/kept" ]; then return; fi
	mkdir -p "$config_home"
	if [ -e "$mimeapps" ]; then cat "$mimeapps"; fi >"$tmp/current"
	# The lines go first into the group, which is added at the end if it is missing; no other line changes.
	awk -v kept="$tmp/kept" '
		function add(line) { while ((getline line < kept) > 0) print line; added = 1 }
		{ print; last = $0 }
		$0 == "[Default Applications]" && !added { add() }
		END {
			if (added) exit
			if (NR && last != "") print ""
			print "[Default Applications]"
			add()
		}' "$tmp/current" >"$tmp/mimeapps.list"
	write_list "$tmp/mimeapps.list"
	entries=$(awk '{ value = substr($0, index($0, "=") + 1) } !seen[value]++ { list = list sep value; sep = ", " }
		END { print list }' "$tmp/kept")
	say "kept $entries as the default browser; make $app the default browser in $by_hand, if you want it."
}

# listed tells whether $2, which is not empty, is one of the entries of the list $1; ";" parts them.
listed() {
	case ";$1;" in
	*";$2;"*) [ -n "$2" ] ;;
	*) return 1 ;;
	esac
}

# write_list puts the list $1 in place of mimeapps.list. An unchanged list is left alone. A changed one is
# written beside the file that the name leads to, with its permissions, and moved over it: a symbolic link
# stays a link, and the old list stays whole until the new one is complete.
write_list() {
	if [ -e "$mimeapps" ] && cmp -s "$1" "$mimeapps"; then return; fi
	target=$(readlink -f -- "$mimeapps")
	part=${target%/*}/.${target##*/}.$app.part
	# A copy of the old list gives the new one its permissions; a list made anew gets the usual ones.
	if ! { { [ ! -e "$target" ] || cp -p -- "$target" "$part"; } && cat "$1" >"$part" && mv -f -- "$part" "$target"; }; then
		rm -f -- "$part"
		fail "cannot write $mimeapps"
	fi
}

# forget takes our entry out of mimeapps.list; the file $1 has a line "type=previous choice" for each
# type that is still ours.
forget() {
	if [ ! -e "$mimeapps" ]; then return; fi
	awk -v ours="$ours" -v records="$1" '
		function without(list, items, count, i, rest) {
			count = split(list, items, ";")
			for (i = 1; i <= count; i++)
				if (items[i] != "" && items[i] != ours) rest = rest items[i] ";"
			return rest
		}
		BEGIN {
			while ((getline line < records) > 0) {
				at = index(line, "=")
				previous[substr(line, 1, at - 1)] = substr(line, at + 1)
			}
		}
		/^\[/ { group = $0 }
		group == "[Default Applications]" || group == "[Added Associations]" {
			at = index($0, "=")
			if (at && index(";" substr($0, at + 1) ";", ";" ours ";")) {
				key = substr($0, 1, at - 1)
				value = without(substr($0, at + 1))
				if (group == "[Default Applications]" && previous[key] != "") value = previous[key]
				if (value == "") next
				$0 = key "=" value
			}
		}
		{ print }' "$mimeapps" >"$tmp/mimeapps.list"
	write_list "$tmp/mimeapps.list"
}

uninstall() {
	lost=0
	: >"$tmp/previous"
	for key in $keys; do
		if ! is_ours "$(chosen "$key")"; then continue; fi
		value=$(recorded "$key")
		if [ "$key" != kdeglobals ]; then
			echo "$key=$value" >>"$tmp/previous"
		elif [ -n "$value" ]; then
			kwriteconfig6 --file kdeglobals --group General --key BrowserApplication "$value" || lost=1
		else
			kwriteconfig6 --file kdeglobals --group General --key BrowserApplication --delete "" || true
		fi
	done
	forget "$tmp/previous"
	rm -f "${bin_dir:?}/${app:?}" "${apps_dir:?}/${ours:?}"
	rm -f "${state_dir:?}/previous-defaults" "${state_dir:?}/last"
	rmdir "${state_dir:?}" 2>/dev/null || true
	if [ "$purge" = 1 ]; then
		rm -f "${config_home:?}/${app:?}/config.toml"
		rmdir "${config_home:?}/${app:?}" 2>/dev/null || true
	fi
	refresh
	# Every choice comes back as it was, even one whose entries are gone; KDE then picks a browser itself.
	if has xdg-mime; then
		while IFS= read -r line; do
			value=${line#*=}
			if [ -n "$value" ] && ! listed "$value" "$(xdg-mime query default "${line%%=*}" </dev/null 2>/dev/null)"; then
				lost=1
			fi
		done <"$tmp/previous"
	fi
	if has xdg-mime && [ -z "$(xdg-mime query default x-scheme-handler/https 2>/dev/null)" ]; then lost=1; fi
	if [ "$lost" = 1 ]; then say "choose another default browser in $by_hand."; fi
	say "removed"
}

main() {
	yes=0 want_default=1 action=install purge=0 version=${KBC_VERSION:-}
	while [ $# -gt 0 ]; do
		case $1 in
		--yes) yes=1 ;;
		--no-default) want_default=0 ;;
		--uninstall) action=uninstall ;;
		--purge) purge=1 ;;
		--version)
			if [ $# -lt 2 ]; then
				usage >&2
				exit 2
			fi
			version=$2
			shift
			;;
		--help)
			usage
			exit
			;;
		*)
			usage >&2
			exit 2
			;;
		esac
		shift
	done
	if [ "$purge" = 1 ] && [ "$action" != uninstall ]; then
		usage >&2
		exit 2
	fi

	check_system
	python=${KBC_PYTHON:-/usr/bin/python3}
	bin_dir=${KBC_INSTALL_DIR:-$HOME/.local/bin}
	apps_dir=${XDG_DATA_HOME:-$HOME/.local/share}/applications
	state_dir=${XDG_STATE_HOME:-$HOME/.local/state}/$app
	config_home=${XDG_CONFIG_HOME:-$HOME/.config}
	mimeapps=$config_home/mimeapps.list
	tmp=$(mktemp -d)
	trap 'rm -rf "${tmp:?}"' EXIT
	trap 'exit 1' INT TERM
	if [ "$action" = uninstall ]; then
		uninstall
		return
	fi

	# With "curl | sh" the standard input is this script, so questions are asked on the terminal.
	tty=0
	terminal=${KBC_TTY:-/dev/tty}
	if (: <"$terminal") 2>/dev/null; then
		exec 3<"$terminal"
		tty=1
	fi
	check_desktop
	check_python
	download
	ensure_pyqt
	note_effective
	place
	if [ "$want_default" = 1 ]; then make_default; fi
	if ! is_chosen; then keep_effective; fi
}

# In braces, so that a download cut short runs nothing.
{
	main "$@"
	exit
}
