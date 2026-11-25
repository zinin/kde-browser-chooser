#!/usr/bin/env python3
"""Breaks a copy of the program in one place at a time and checks that a test notices."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTEST = [sys.executable, "-B", "-m", "pytest", "-q", "-x", "--tb=no"]

# file, what is broken, old text, new text, tests that must fail (pytest -k)
MUTATIONS = [
    ("desktop", "hidden entries are browsers", '("NoDisplay", "Hidden", "Terminal")', '("Hidden", "Terminal")', "not_a_browser"),
    ("desktop", "the user's entry does not win", ' and entry_id not in seen', "", "masks"),
    ("desktop", "snap and flatpak are not searched", ", *(path.replace(\"~\", home, 1) for path in EXTRA_DATA_DIRS)", "", "snap_and_flatpak"),
    ("desktop", "one browser twice", "tiles.setdefault(tile.command, tile)", "tiles[(tile.id,)] = tile", "same_command"),
    ("desktop", "names are not localized", 'fields.get(f"Name[{language}]") or ', "", "localized"),
    ("desktop", "it offers itself", "entry_id in NOT_BROWSERS or ", "", "excludes_itself"),
    ("desktop", "a program without links is a browser", "if name and takes_url(command)", "if name", "not_a_browser"),
    ("desktop", "percent signs in names", '"%c": name.replace("%", "%%")', '"%c": name', "percent"),
    ("i18n", "only LANG counts", '("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")', '("LANG",)', "pick_language"),
    ("i18n", "missing texts stay missing", "read_locale(DEFAULT) | read_locale(language)", "read_locale(language)", "missing_string"),
    ("config", "unknown settings pass", 'check_keys(table, {"language", "order", "hide", "rename", "tile"})', "pass", "bad_config"),
    ("config", "a BOM breaks the file", '"utf-8-sig"', '"utf-8"', "bom"),
    ("config", "own tiles lose the link", 'else [*argv, "%U"]', "else argv", "test_command"),
    ("config", "reserved ids pass", " or tile_id in RESERVED_IDS", "", "bad_config"),
    ("tiles", "copying without a link", " if has_link else []", "", "no_link"),
    ("tiles", "order is ignored", "[*config.order, *tiles]", "[*tiles]", "order_first"),
    ("tiles", "hide is ignored", " if tile_id not in config.hide", "", "test_hide"),
    ("state", "an unknown last choice", 'return last if last in ids else next(iter(ids), "")', "return last", "unknown_last"),
    ("state", "the last choice loses its trailing space", '.removesuffix("\\n")', ".strip()", "trailing_space"),
    ("actions", "SIGPIPE stays ignored", "    signal.signal(signal.SIGPIPE, signal.SIG_DFL)\n", "", "launch_replaces"),
    ("actions", "%u gets all links at once", "if per_link else [urls]", "if False else [urls]", "test_expand"),
    ("actions", "wl-copy on X11", 'bool(os.environ.get("WAYLAND_DISPLAY")) and ', "", "x11"),
    ("actions", "a failed copy is a success", "return 0 if copied else 1", "return 0", "copy_failure"),
    ("notify", "lost notifications are silent", "if not shown:", "if False:", "never_raises"),
    ("notify", "the body is read as markup", "html.escape(body, quote=False)", "body", "not_markup"),
    ("dbus", "quotes reach gdbus raw", '.replace("\'", "\\\\\'")', "", "gdbus"),
    ("fallback", "the cursor is not on the last choice", "by_id[last].title", "last", "cursor"),
    ("fallback", "a kdialog failure is a cancel", "if result.returncode == 1:", "if result.returncode:", "failure_is_not"),
    ("fallback", "links are read as HTML", "html.escape(shown, quote=False)", "shown", "test_menu"),
    ("fallback", "items are taken for options", '"--", *menu', "*menu", "look_like_options"),
    ("fallback", "an unknown answer is a cancel", 'raise RuntimeError(f"kdialog answered {answer!r}")', "return None", "unknown_answer"),
    ("fallback", "an id loses its trailing space", 'result.stdout.removesuffix("\\n")', "result.stdout.strip()", "trailing_space"),
    ("window", "no guard against double clicks", "armed = shown.isValid() and shown.hasExpired(GUARD_MS)", "armed = True", "guard"),
    ("window", "the guard counts the release", "if picked or not armed:", "if picked or not shown.hasExpired(GUARD_MS):", "counts_the_press"),
    ("window", "a shorter guard", "GUARD_MS = 300", "GUARD_MS = 120", "guard"),
    ("window", "a second click wins", "if picked or not", "if not", "second_click"),
    ("window", "copying waits for a token", "if tile and tile.command:", "if True:", "copy_and_cancel"),
    ("window", "no highlight", "            button.setPalette(highlighted(button.palette()))\n", "", "highlighted"),
    ("window", "no focus on the last choice", "            button.setFocus()\n", "", "enter_opens"),
    ("window", "Enter does nothing", "(Qt.Key.Key_Return, Qt.Key.Key_Enter)", "(Qt.Key.Key_F12,)", "enter_opens"),
    ("window", "links are rich text", "    text.setTextFormat(Qt.TextFormat.PlainText)\n", "", "literal"),
    ("window", "long links widen the window", "metrics.elidedText(label, Qt.TextElideMode.ElideRight, room)", "label", "long_link"),
    ("window", "always three columns", "return 2 if count <= 4 else 3 if count <= 9 else 4", "return 3", "columns"),
    ("window", "ampersands are shortcuts", '.replace("&", "&&")', "", "ampersand"),
    ("window", "missing icons stay empty", "return QIcon.fromTheme(ICON) if found.isNull() else found", "return found", "missing_icon"),
    ("window", "a closed window still opens the link", "return picked if window.exec() else None", "window.exec()\n    return picked", "escape_while"),
    ("window", "KWin does not know the program", '    app.setDesktopFileName("kde-browser-chooser")\n', "", "desktop_file_name"),
    ("window", "arrows do not follow the grid", "        group.addButton(button)\n", "", "arrows"),
    ("activation", "waits for a token forever", "        QTimer.singleShot(TOKEN_WAIT_MS, done)\n", "", "no_fresh_token"),
    ("activation", "a failure aborts the program", "\n    except Exception:  # out of", "\n    except KeyError:  # out of", "broken_kde"),
    ("activation", "a token that cannot be used aborts the program", "        except Exception:  # out of", "        except KeyError:  # out of", "cannot_be_used"),
    ("activation", "an empty token replaces the old one", "        if token:\n", "        if True:\n", "no_fresh_token"),
    ("cli", "no fallback", "    except Exception:\n        log_exception()\n        picked", "    except KeyError:\n        log_exception()\n        picked", "falls_back"),
    ("cli", "an unexpected failure is silent", "    except Exception:  # the last resort", "    except KeyError:  # the last resort", "unexpected or nothing_works"),
    ("cli", "the browser gets no fresh token", "        if token:\n", "        if False:\n", "token_of_the_window"),
    ("child", "a crash is a cancel", "if status or not answer:", "if False:", "crash_is"),
    ("child", "the window outlives the program", "ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)", "pass", "outlive or ctrl_c"),
    ("config", "a deep settings file blocks links", "(OSError, ValueError, RecursionError)", "(OSError, ValueError)", "too_deep"),
    ("state", "an odd id loses the link", "with contextlib.suppress(OSError, ValueError):", "with contextlib.suppress(OSError):", "odd_id"),
    ("actions", "an impossible command loses the link", "except (OSError, ValueError) as error:", "except OSError as error:", "impossible"),
    ("cli", "the choice is not remembered", "    state.save_last(last_file, picked.id)\n", "", "remembers"),
    ("cli", "a bad settings file is silent", "    if error:\n", "    if False:\n", "config_error"),
    ("cli", "links that look like options", 'case ["--list"]:', 'case ["--list", *_]:', "options_work_only"),
    ("cli", "Ctrl+C does not work", "signal.signal(signal.SIGINT, signal.SIG_DFL)", "pass", "ctrl_c"),
    ("cli", "an ignored SIGCHLD stays ignored", "signal.signal(signal.SIGCHLD, signal.SIG_DFL)", "pass", "sigchld"),
    ("cli", "no counter of links", "if len(urls) > 1:", "if False:", "remembers"),
    ("log", "a closed stderr loses the link", "contextlib.suppress(Exception)", "contextlib.suppress(KeyError)", "dead_stderr"),
    ("../../tools/build", "other people's PYTHONPATH", 'b"#!/usr/bin/python3 -I\\n"', 'b"#!/usr/bin/python3\\n"', "runs_isolated"),
    ("../../install.sh", "checksums are not checked", 'if [ -z "$want" ] || [ "$got" != "$want" ]; then', "if false; then", "bad_checksum"),
    ("../../install.sh", "it remembers itself", 'if is_ours "$value"; then value=$(recorded "$key"); fi', ":", "follow_the_user"),
    ("../../install.sh", "being there counts as being chosen", 'is_ours "$(chosen x-scheme-handler/http)" && is_ours "$(chosen x-scheme-handler/https)"', '[ "$(xdg-mime query default x-scheme-handler/https)" = "$ours" ]', "none_was_chosen"),
    ("../../install.sh", "quotes around the program", "/usr/bin/env \"%s\"", "\"%s\"", "unusual_home"),
    ("../../install.sh", "a broken update stays", 'if ! installed=$("$new" --version); then', "installed=; if false; then", "does_not_run"),
    ("../../install.sh", "Ctrl+D means yes", "|| answer=n # Ctrl+D", "|| answer=", "answer_no"),
    ("../../install.sh", "--purge alone installs", 'if [ "$purge" = 1 ] && [ "$action" != uninstall ]; then', "if false; then", "bad_options"),
    ("../../install.sh", "our entry stays in the lists", "if (value == \"\") next", "if (value == \"\") value = ours", "leaves_nothing"),
    ("../../install.sh", "uninstalling takes others' places", 'if ! is_ours "$(chosen "$key")"; then continue; fi', ":", "still_ours"),
    ("../../install.sh", "root may install", '[ "$(id -u)" -ne 0 ] ||', "true ||", "root_is_refused"),
    ("../../install.sh", "a list is suggested as the default", "suggested=n", "suggested=y", "only_kdialog"),
    ("../../install.sh", "the running file is overwritten", 'mv -f "$new" "$bin_dir/$app"', 'cp "$new" "$bin_dir/$app"', "atomically"),
    ("../../install.sh", "ostree systems get dnf", '[ -e "${KBC_SYSROOT:-}/run/ostree-booted" ]', "false", "ostree"),
]


def target(name: str) -> Path:
    path = Path("src/kde_browser_chooser", name)
    return Path(os.path.normpath(path if path.suffix else f"{path}.py"))


def main() -> int:
    survived = 0
    with tempfile.TemporaryDirectory() as copy:
        for item in ("src", "tests", "tools", "install.sh", "pyproject.toml", "config.example.toml"):
            source = ROOT / item
            (shutil.copytree if source.is_dir() else shutil.copy)(source, Path(copy, item))
        # Without pytest, or with tests that fail anyway, every mutation would look noticed.
        result = subprocess.run(PYTEST, cwd=copy, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(*[line for line in (result.stdout + result.stderr).splitlines() if line.strip()][-10:],
                  f"the tests do not pass unmutated (pytest exited with {result.returncode}), so nothing is checked",
                  sep="\n", file=sys.stderr)
            return 1
        for name, what, old, new, tests in MUTATIONS:
            path = Path(copy, target(name))
            original = path.read_text()
            assert original.count(old) == 1, (name, what, original.count(old))
            path.write_text(original.replace(old, new))
            result = subprocess.run([*PYTEST, "-k", tests], cwd=copy, capture_output=True, text=True, timeout=120)
            path.write_text(original)
            noticed = result.returncode == 1  # only failed tests; 5 is "no test selected"
            survived += not noticed
            summary = [line for line in result.stdout.splitlines() if line.strip()][-1:] or [f"exit {result.returncode}"]
            if result.returncode not in (0, 1, 5):  # 2 interrupted, 3 internal error, 4 usage error, or a signal
                summary = [f"error: pytest exited with {result.returncode}"]
            print("noticed " if noticed else "SURVIVED", "|", target(name).name, "|", what, "|", summary[0], flush=True)
    print(f"survived: {survived} of {len(MUTATIONS)}")
    return bool(survived)


if __name__ == "__main__":
    sys.exit(main())
