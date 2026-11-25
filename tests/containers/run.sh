#!/bin/sh
# run.sh [IMAGE...] tries the installer in containers of the main distributions.
set -eu
cd "$(dirname "$0")/../.."
dist=$(mktemp -d)
trap 'rm -rf "$dist"' EXIT
python3 tools/build.py --out "$dist"
chmod -R a+rX "$dist"
[ $# -gt 0 ] || set -- ubuntu:26.04 debian:13 fedora:latest archlinux:latest opensuse/tumbleweed:latest
failed=0
for image; do
	if docker run --rm -v "$PWD/install.sh:/src/install.sh:ro" -v "$PWD/tests/containers/check.sh:/src/check.sh:ro" \
		-v "$dist:/dist:ro" "$image" sh /src/check.sh >"$dist/log" 2>&1; then
		echo "OK $image"
	else
		echo "FAILED $image"
		tail -n 30 "$dist/log"
		failed=1
	fi
done
exit $failed
