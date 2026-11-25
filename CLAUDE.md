# kde-browser-chooser

The default browser of a KDE Plasma 6 session: shows the installed browsers as tiles, then becomes the
chosen one. Standard library and the distribution's PyQt6 only; everything else is optional.

## Commands

- Tests: `python3 -m pytest` (offscreen; nothing of the real user is touched).
- Build: `python3 tools/build.py` writes `dist/`, reproducibly.
- Mutations: `python3 tools/mutate.py` must end with `survived: 0`; add a line for new behaviour.
- Installer in containers: `tests/containers/run.sh [IMAGE...]`.
- Browser comes to the front: `tests/kwin/focus.sh`, on a machine with Plasma 6 (see its README).
- Shell: `shellcheck install.sh tests/*/*.sh`.

## Rules

- A link must never be lost silently: window, else kdialog, else a notification with the link. An
  exception in a Qt slot aborts the process, so slots catch everything.
- `cli` imports every module of the package; PyQt6 is imported only inside `window.pick` and
  `activation`. An update replaces the archive under an open window, and without PyQt6 the fallback
  must still work.
- `actions.become` passes `os.environ`, not the process environment: Qt removes the token from the latter.
- Texts live in `locales/*.toml`, every key in every file.
- Code, comments and commit messages are in English.
- No personal data in the repository or its history.

## Release

Set `__version__` and `CHANGELOG.md` in one commit on `master`, then push an annotated tag `vX.Y.Z`;
its message becomes the release notes. `install.sh` is read from `master`, the program from the latest release.
