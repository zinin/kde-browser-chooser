#!/usr/bin/env python3
"""Builds the release files: the program as one executable file, its desktop entry and the checksums."""
import argparse
import hashlib
import io
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PACKAGE = SRC / "kde_browser_chooser"
SHEBANG = b"#!/usr/bin/python3 -I\n"


def archive() -> bytes:
    files = {"__main__.py": PACKAGE / "__main__.py"}
    files |= {str(path.relative_to(SRC)): path for pattern in ("*.py", "locales/*.toml") for path in PACKAGE.glob(pattern)}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for name in sorted(files):
            # A fixed date and mode make the result reproducible.
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr, info.compress_type = 0o644 << 16, zipfile.ZIP_DEFLATED
            target.writestr(info, files[name].read_bytes())
    return SHEBANG + buffer.getvalue()


def desktop_entry() -> bytes:
    locales = {path.stem: tomllib.loads(path.read_text("utf-8")) for path in sorted(PACKAGE.glob("locales/*.toml"))}
    english = locales.pop("en")
    lines = ["[Desktop Entry]", "Type=Application"]
    for key, field in (("desktop_name", "Name"), ("desktop_comment", "Comment")):
        lines.append(f"{field}={english[key]}")
        lines += [f"{field}[{language}]={texts[key]}" for language, texts in locales.items() if key in texts]
    lines += ["Exec=@EXEC@ -- %U", "Icon=internet-web-browser", "Terminal=false", "Categories=Network;WebBrowser;",
              "MimeType=x-scheme-handler/http;x-scheme-handler/https;text/html;application/xhtml+xml;"]
    return "\n".join([*lines, ""]).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    files = {"kde-browser-chooser": archive(), "kde-browser-chooser.desktop": desktop_entry()}
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / "kde-browser-chooser").chmod(0o755)
    (out / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items()))
    print(f"built in {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
