import string

import pytest

from kde_browser_chooser import i18n


@pytest.mark.parametrize("configured, env, want", [
    (None, {}, "en"),
    (None, {"LANG": "ru_RU.UTF-8"}, "ru"),
    (None, {"LANG": "ru"}, "ru"),
    (None, {"LANGUAGE": "de:ru", "LANG": "en_US.UTF-8"}, "ru"),
    (None, {"LANGUAGE": "", "LANG": "ru_RU.UTF-8"}, "ru"),
    (None, {"LANG": "C.UTF-8"}, "en"),
    (None, {"LC_ALL": "en_US.UTF-8", "LANG": "ru_RU.UTF-8"}, "en"),
    (None, {"LC_MESSAGES": "ru_RU@mod", "LANG": "en_US.UTF-8"}, "ru"),
    (None, {"LANG": "de_DE.UTF-8"}, "en"),
    ("ru", {"LANG": "en_US.UTF-8"}, "ru"),
    ("en", {"LANG": "ru_RU.UTF-8"}, "en")])
def test_pick_language(configured, env, want):
    assert i18n.pick_language(configured, env) == want


def fields(text):
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name)


def test_english_and_russian_are_available():
    assert {"en", "ru"} <= i18n.AVAILABLE


@pytest.mark.parametrize("language", sorted(i18n.AVAILABLE))
def test_locale_matches_english(language):
    english, own = i18n.load_strings("en"), i18n.read_locale(language)
    assert own.keys() == english.keys()
    assert {key: fields(text) for key, text in own.items()} == {key: fields(text) for key, text in english.items()}


def test_texts():
    assert i18n.load_strings("en")["title"] == "Open link"
    assert i18n.load_strings("ru")["title"] == "Открыть ссылку"


def test_missing_string_is_english(tmp_path, monkeypatch):
    (tmp_path / "en.toml").write_text('title = "Open"\ncancel = "Cancel"\n')
    (tmp_path / "xx.toml").write_text('title = "Xopen"\n')
    monkeypatch.setattr(i18n, "LOCALES", tmp_path)
    assert i18n.load_strings("xx") == {"title": "Xopen", "cancel": "Cancel"}
