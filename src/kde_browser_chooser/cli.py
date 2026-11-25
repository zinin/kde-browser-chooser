import os
import shlex
import signal
import sys
from dataclasses import replace

from . import __version__, actions, config, desktop, fallback, i18n, paths, state, tiles, window
from .log import log_exception
from .model import Tile
from .notify import notify

HELP = f"""\
Usage: kde-browser-chooser [--] [URL...]
       kde-browser-chooser --list | --version | --help

Asks in which browser to open the links. Meant to be the default browser.

  --list     print the tiles: id, title, command, icon
  --version  print the version
  --help     print this help

Settings: {paths.config_file({"HOME": "~"})} (optional)"""


def load(urls: list[str], settings: config.Config) -> tuple[list[Tile], dict[str, str]]:
    language = i18n.pick_language(settings.language, os.environ)
    strings = i18n.load_strings(language)
    return tiles.build(desktop.find_browsers(os.environ, language), settings, strings, bool(urls)), strings


def choose(urls: list[str]) -> int:
    settings, error = config.Config(), None
    try:
        settings = config.load(paths.config_file(os.environ))
    except config.ConfigError as problem:
        error = problem
    choices, strings = load(urls, settings)
    if error:
        notify("dialog-warning", strings["config_error"], f"{paths.config_file(os.environ)}: {error}")

    label = urls[0] if urls else strings["no_link"]
    if len(urls) > 1:
        label += " " + strings["more_links"].format(n=len(urls) - 1)
    last_file = paths.last_file(os.environ)
    last = state.read_last(last_file, choices)
    try:
        picked = window.pick(choices, label, last, strings)
    except Exception:
        log_exception()
        try:
            picked = fallback.pick_with_kdialog(choices, label, last, strings)
        except Exception:
            log_exception()
            notify("dialog-error", strings["window_failed"], "\n".join(urls))
            return 1
    if picked is None:
        return 0
    state.save_last(last_file, picked.id)
    return actions.launch(picked, urls, strings) if picked.command else actions.copy(urls, strings)


def print_list() -> int:
    try:
        settings = config.load(paths.config_file(os.environ))
    except config.ConfigError as error:
        print(f"{paths.config_file(os.environ)}: {error}", file=sys.stderr)
        return 1
    for tile in load(["a link"], replace(settings, hide=frozenset()))[0]:
        print(tile.id, tile.title, shlex.join(tile.command or ()), tile.icon, sep="\t")
    return 0


def main(argv: list[str]) -> int:
    match argv:  # a link handler must not stumble over odd arguments: an option counts only alone
        case ["--list"]:
            return print_list()
        case ["--version"]:
            print(f"kde-browser-chooser {__version__}")
            return 0
        case ["--help"]:
            print(HELP)
            return 0
        case ["--", *urls]:
            return choose(urls)
    return choose(argv)


def run() -> None:
    if signal.getsignal(signal.SIGINT) is signal.default_int_handler:
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # Python would see Ctrl+C only after the window is closed
    sys.exit(main(sys.argv[1:]))
