"""Texts in the user's language: one file in locales/ per language."""
import re
import tomllib
from collections.abc import Mapping
from importlib import resources

LOCALES = resources.files(__package__) / "locales"
AVAILABLE = frozenset(file.name.removesuffix(".toml") for file in LOCALES.iterdir() if file.name.endswith(".toml"))
DEFAULT = "en"


def pick_language(configured: str | None, env: Mapping[str, str]) -> str:
    if configured:
        return configured
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for locale in env.get(variable, "").split(":"):
            language = re.split("[_.@]", locale)[0]
            if language in AVAILABLE:
                return language
    return DEFAULT


def read_locale(language: str) -> dict[str, str]:
    return tomllib.loads((LOCALES / f"{language}.toml").read_text(encoding="utf-8"))


def load_strings(language: str) -> dict[str, str]:
    return read_locale(DEFAULT) | read_locale(language)
