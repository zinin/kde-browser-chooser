# kde-browser-chooser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** программа для KDE Plasma 6, которая на клик по ссылке показывает плитки установленных браузеров; ставится командой `curl … | sh`.

**Architecture:** пакет `kde_browser_chooser` (стандартная библиотека + PyQt6 дистрибутива), собранный в один исполняемый zipapp. Плитки строятся при каждом запуске из записей `.desktop` и необязательного TOML. Выбор — окно PyQt6, запасной путь — kdialog, последний рубеж — уведомление; затем процесс заменяется браузером. POSIX-установщик кладёт файл в `~/.local` и назначает браузером по умолчанию.

**Tech Stack:** Python ≥ 3.11, PyQt6 ≥ 6.7, libKF6WindowSystem через ctypes, pytest, POSIX sh, shellcheck, GitHub Actions, docker.

**Spec:** `docs/superpowers/specs/2026-11-25-kde-browser-chooser-design.md`

## Global Constraints

- Запуск — `/usr/bin/python3 -I`; обязательна только PyQt6 из пакета дистрибутива.
- Код, комментарии, имена тестов, сообщения коммитов, `CLAUDE.md` — по-английски; тексты окна — только из `locales/*.toml`.
- Личных данных автора нет нигде, включая историю коммитов.
- Ветка `feat/initial` (`git switch -c`); публичные шаги — только в задаче 10.
- Все модули пакета импортируются при импорте `cli`; PyQt6 — только внутри `window.pick` и `activation`.
- Тесты не трогают настоящие настройки, буфер, браузеры и уведомления: `HOME`/`XDG_*` временные, внешние команды подставные, `QT_QPA_PLATFORM=offscreen`.
- Прежний скрипт и его тесты — источник переноса (их место — в личном документе автора); поведение из раздела дизайна «Что переносится» обязательно.

## Review Focus

1. `Exec=env VAR=… /snap/bin/firefox %u` — обёртка запускается, а не теряется (задачи 1, 4).
2. В настройках не тот тип (`hide = "opera"`), пустой файл, BOM — окно работает, приходит уведомление или ничего (задача 3).
3. Повторная установка не затирает запомненный прежний браузер нашим же ID (задача 7).
4. Домашняя папка с пробелом — `Exec` в записи и установка не ломаются (задача 7).
5. Нет `xdg-settings` — установка завершается и говорит, как назначить вручную (задача 7).

---

### Task 1: Репозиторий и поиск браузеров

**Files:** Create: `LICENSE`, `.gitignore`, `README.md` (заглушка), `pyproject.toml` (`pythonpath = ["src"]` для pytest), `src/kde_browser_chooser/__init__.py` (`__version__ = "0.1.0"`), `src/kde_browser_chooser/model.py`, `src/kde_browser_chooser/desktop.py`, `docs/superpowers/{specs,plans}/…`; Test: `tests/test_desktop.py`, `tests/conftest.py`

**Interfaces — Produces:**
- `model.Tile` — frozen dataclass: `id: str, title: str, icon: str, command: tuple[str, ...] | None` (`None` — копировать; в `command` остаются `%%` и URL-коды `%u %U %f %F`)
- `desktop.application_dirs(env: Mapping[str, str]) -> list[Path]`
- `desktop.parse_exec(value: str, *, icon: str, name: str, path: str) -> tuple[str, ...]` — `ValueError` при незакрытой кавычке
- `desktop.find_browsers(env: Mapping[str, str], language: str) -> list[Tile]`
- `conftest.py`: `apps` (`apps.add(id, system=True, **fields)` пишет запись во временный XDG-каталог), `env`, `fakes` (подставные команды — перенос)

- [ ] **Step 1: Подготовить репозиторий локально:** `git init -b master`, коммит LICENSE (MIT, правообладатель как в `graft`), `.gitignore`, README-заглушки; `git switch -c feat/initial`; коммит вычищенных дизайна и плана.
- [ ] **Step 2: Написать тесты**

```python
FIREFOX = dict(Type="Application", Name="Firefox", Exec="firefox %u", Icon="firefox",
               MimeType="text/html;x-scheme-handler/https;")

def test_browser_found():         # == [Tile("firefox", "Firefox", "firefox", ("firefox", "%u"))]
@pytest.mark.parametrize("change", [{"NoDisplay": "true"}, {"Hidden": "true"}, {"Terminal": "true"},
    {"Type": "Link"}, {"MimeType": "text/html;"}, {"OnlyShowIn": "GNOME;"}, {"NotShowIn": "KDE;"},
    {"TryExec": "/nonexistent"}, {"Exec": "firefox"}, {"Exec": '"open %u'}, {"Exec": None}])
def test_not_a_browser(change):   assert find_browsers(env, "en") == []
def test_user_entry_masks_system_one():      # Hidden=true у пользователя, тот же ID в системе → []
def test_subdirectory_becomes_id():          # vendor/x.desktop → "vendor-x"
def test_snap_and_flatpak_dirs_added_once(): # каждый из трёх каталогов ровно один раз
def test_same_command_is_one_tile():         # google-chrome и com.google.Chrome, оба видимы → 1
def test_localized_name():                   # Name[ru]="Лиса": "ru" → "Лиса", "en" → "Firefox"
def test_excludes_itself_and_old_script():   # kde-browser-chooser, browser-chooser
def test_sorted_by_title():       assert titles == ["Firefox", "Google Chrome", "yandex"]
@pytest.mark.parametrize("data", [b"\xff\xfe\x00", b"", b"[Other]\nExec=x %u\n"])
def test_garbage_is_ignored(data): assert find_browsers(env, "en") == []
@pytest.mark.parametrize("value, argv", [
    ("firefox %u", ("firefox", "%u")), ('"/opt/a b/x" --new %U', ("/opt/a b/x", "--new", "%U")),
    ("env A=b /snap/bin/firefox %u", ("env", "A=b", "/snap/bin/firefox", "%u")),
    ("x --url=%u", ("x", "--url=%u")), ("x %% %c %k %i %u", ("x", "%%", "N", "/p", "--icon", "I", "%u")),
    ("x %d %m %u", ("x", "%u")), ("flatpak run o @@u %u @@", ("flatpak", "run", "o", "@@u", "%u", "@@"))])
def test_parse_exec(value, argv): assert parse_exec(value, icon="I", name="N", path="/p") == argv
```

- [ ] **Step 3: Прогнать** `python3 -m pytest -q` — FAIL (нет `desktop`).
- [ ] **Step 4: Реализовать** по правилам раздела дизайна «Плитки» 2–4 (KDE — по `XDG_CURRENT_DESKTOP`, по умолчанию `KDE`; `TryExec` ищется в `PATH`).
- [ ] **Step 5: Прогнать** — PASS. **Commit:** `feat: find installed browsers`

### Task 2: Тексты и язык

**Files:** Create: `src/kde_browser_chooser/i18n.py`, `src/kde_browser_chooser/locales/{en,ru}.toml`; Test: `tests/test_i18n.py`

**Interfaces — Produces:** `i18n.AVAILABLE: frozenset[str]`; `i18n.pick_language(configured: str | None, env: Mapping[str, str]) -> str`; `i18n.load_strings(language: str) -> dict[str, str]`. Ключи: `title` («Open link» / «Открыть ссылку»), `copy`, `cancel`, `no_link`, `more_links` (`(+{n})`), `copied`, `copy_failed`, `launch_failed` (`{name}`), `window_failed`, `config_error`, `desktop_name`, `desktop_comment`. Русские тексты — из прежнего скрипта и его записи.

- [ ] **Step 1: Написать тесты**

```python
@pytest.mark.parametrize("configured, env, want", [(None, {}, "en"), (None, {"LANG": "ru_RU.UTF-8"}, "ru"),
    (None, {"LANGUAGE": "de:ru", "LANG": "en_US.UTF-8"}, "ru"), (None, {"LANG": "C.UTF-8"}, "en"),
    (None, {"LC_ALL": "en_US.UTF-8", "LANG": "ru_RU.UTF-8"}, "en"), (None, {"LANG": "de_DE.UTF-8"}, "en"),
    ("ru", {"LANG": "en_US.UTF-8"}, "ru"), ("en", {"LANG": "ru_RU.UTF-8"}, "en")])
def test_pick_language(configured, env, want): assert pick_language(configured, env) == want
def test_locales_match_english():     # у каждой локали тот же набор ключей и подстановок {…}
def test_missing_string_is_english(): # локаль без "cancel" → английское значение
```

- [ ] **Step 2: Прогнать** — FAIL. **Step 3: Реализовать** (чтение через `importlib.resources`, чтобы работало из zipapp). **Step 4: Прогнать** — PASS. **Commit:** `feat: English and Russian texts`

### Task 3: Настройки, порядок плиток, прошлый выбор

**Files:** Create: `src/kde_browser_chooser/{paths,config,tiles,state}.py`, `config.example.toml`; Test: `tests/test_config.py`, `tests/test_tiles.py`

**Interfaces — Produces:**
- `paths.config_file(env) -> Path`, `paths.last_file(env) -> Path`
- `config.Config` (frozen): `language: str | None, order: tuple[str, ...], hide: frozenset[str], rename: dict[str, str], tiles: tuple[Tile, ...]`; `config.load(path) -> Config` (нет файла — пустой); `config.ConfigError` (текст — для уведомления)
- `tiles.build(browsers: list[Tile], config: Config, strings: dict[str, str], has_link: bool) -> list[Tile]` (без «Отмены»); ID копирования — `"copy"`
- `state.read_last(path, tiles: list[Tile]) -> str` (неизвестное — ID первой плитки, нет плиток — `""`), `state.save_last(path, tile_id: str) -> None` (ошибки молча)

- [ ] **Step 1: Написать тесты**

```python
def test_example_file_loads():                # config.example.toml читается без ошибок
def test_no_file_and_empty_file():            assert load(path) == Config()
@pytest.mark.parametrize("text", ['hide = "opera"', 'order = [1]', 'oops = 1', 'language = "xx"', 'rename = []',
    '[[tile]]\nname = "x"', '[[tile]]\ncommand = "x"', '[[tile]]\nid = "copy"\nname = "x"\ncommand = "x"',
    '[[tile]]\nname = "x"\ncommand = "\'"', 'order = ['])
def test_bad_config(text):                    # ConfigError; текст называет ключ или строку
def test_bom_is_accepted():                   # "﻿hide = []"
def test_custom_tile():    # command 'x --p "a b"' → ("x", "--p", "a b", "%U"); с %u — без добавления; id "Chrome: работа" → "chrome-работа"
def test_default_order():                     assert ids == ["copy", "chrome", "firefox", "mine"]
def test_order_first_then_rest():             # order=["firefox","copy","gone"] → ["firefox","copy","chrome","mine"]
def test_hide_and_rename():                   # hide copy и chrome; rename firefox → "Лис"
def test_custom_tile_replaces_browser_with_same_id():
def test_no_link_no_copy():                   # has_link=False
def test_last_roundtrip(); def test_unknown_last_is_first_tile(); def test_unwritable_state_is_ignored()
```

- [ ] **Step 2: Прогнать** — FAIL. **Step 3: Реализовать** (`tomllib`; `language` проверяется по `i18n.AVAILABLE`; `command` — `shlex.split`). **Step 4: Прогнать** — PASS. **Commit:** `feat: optional settings file`

### Task 4: Уведомления, копирование, запуск

**Files:** Create: `src/kde_browser_chooser/{dbus,notify,actions,log}.py`; Test: `tests/test_actions.py`

**Interfaces — Produces:**
- `dbus.call(service, path, interface, method, signature: str, args: list[str]) -> bool` — `busctl --user`, нет его — `gdbus`; таймаут 5 с; ошибки → `False`
- `notify.notify(icon, summary, body) -> None` — `notify-send`, нет или сбой → `org.freedesktop.Notifications`; не бросает
- `actions.expand(command: tuple[str, ...], urls: list[str]) -> list[list[str]]`
- `actions.copy(urls, strings) -> int`; `actions.launch(tile, urls, strings) -> int` (при успехе не возвращается)
- `log.log_exception() -> None` — перенос

- [ ] **Step 1: Написать тесты**

```python
@pytest.mark.parametrize("command, urls, argvs", [
    (("x", "%U"), ["a", "b"], [["x", "a", "b"]]), (("x", "%u"), ["a", "b"], [["x", "a"], ["x", "b"]]),
    (("x", "--url=%u"), ["a"], [["x", "--url=a"]]), (("x", "%u", "%%"), [], [["x", "%"]]),
    (("f", "@@u", "%u", "@@"), ["a"], [["f", "@@u", "a", "@@"]])])
def test_expand(command, urls, argvs): assert expand(command, urls) == argvs
def test_launch_replaces_process():           # перенос test_browser_launch: токен, SIGPIPE/SIGXFSZ, fd 0–2 и только
def test_launch_resolves_path_and_env():      # команда без пути и обёртка env A=b находятся в PATH
def test_two_links_start_two_processes():     # %u, 2 ссылки: первый процесс запущен, второй заменил наш
def test_missing_program_is_reported():       # код 1, уведомление launch_failed с именем
def test_copy_wl_copy_first():                # WAYLAND_DISPLAY и wl-copy: байт в байт, Klipper не вызван
def test_copy_klipper_without_wl_copy():      # busctl: org.kde.klipper … setClipboardContents s "a\nb"
def test_copy_on_x11_uses_klipper(); def test_copy_failure_is_reported():  # код 1, copy_failed, не copied
def test_notify_falls_back_to_dbus(); def test_notify_never_raises()       # ни notify-send, ни busctl, ни gdbus
def test_gdbus_quoting():                     # тело с ' и \ доходит буквально
```

- [ ] **Step 2: Прогнать** — FAIL. **Step 3: Реализовать**; `launch`: для N argv первые N−1 — `Popen(start_new_session=True)`, последний — `os.execvpe` с `os.environ`. **Step 4: Прогнать** — PASS. **Commit:** `feat: copy links and launch browsers`

### Task 5: Окно и токен активации

**Files:** Create: `src/kde_browser_chooser/{window,activation}.py`; Test: `tests/test_window.py`

**Interfaces — Consumes:** `Tile`, `log`. **Produces:** `window.pick(tiles: list[Tile], label: str, last: str, strings) -> Tile | None`; `window.GUARD_MS = 300`, `window.columns(count: int) -> int`; `activation.request_token(window, done) -> None`, `activation.kwayland_extras()`, `activation.TOKEN_WAIT_MS = 300`

- [ ] **Step 1: Перенести все тесты окна прежнего скрипта и добавить новые**

```python
@pytest.mark.parametrize("count, want", [(2, 2), (4, 2), (5, 3), (6, 3), (9, 3), (10, 4), (16, 4)])
def test_columns(count, want): assert columns(count) == want       # count вместе с «Отменой»
def test_cancel_is_always_last():             # 2, 5 и 8 плиток
def test_missing_icon_file_gets_default():    # путь, которого нет: значок не пустой
def test_guard_is_exactly_300_ms():           # 280 мс — клик не принят, 340 мс — принят
def test_window_is_gone_before_return():      # после pick() окно не видно и событие доставлено
def test_desktop_file_name():                 # QGuiApplication.desktopFileName() == "kde-browser-chooser"
def test_kwayland_extras_signatures():        # в метаобъекте KWaylandExtras есть requestXdgActivationToken(QWindow*,uint32_t,QString), lastInputSerial(QWindow*), сигнал xdgActivationTokenArrived(int,QString); нет библиотеки — skip
```

- [ ] **Step 2: Прогнать** — FAIL. **Step 3: Реализовать** переносом; у `kwayland_extras` — комментарий, почему вызов держится на регистрации `uint32_t` в QtWayland и чем кончается её отсутствие (безопасный отказ). **Step 4: Прогнать** — PASS. **Commit:** `feat: tile window`

### Task 6: Командная строка, запасной путь, сборка

**Files:** Create: `src/kde_browser_chooser/{fallback,cli,__main__}.py`, `tools/build.py`; Test: `tests/test_fallback.py`, `tests/test_cli.py`, `tests/test_build.py`

**Interfaces — Produces:** `fallback.pick_with_kdialog(tiles, label, last, strings) -> Tile | None`; `cli.main(argv: list[str]) -> int`; `tools/build.py --out DIR` → `DIR/kde-browser-chooser` (zipapp, 755), `DIR/kde-browser-chooser.desktop` (`Exec=@EXEC@ -- %U`, Name/Comment из всех локалей), `DIR/SHA256SUMS`; сборка воспроизводима (одинаковые байты при повторе).

- [ ] **Step 1: Написать тесты**

```python
# fallback: перенос тестов kdialog; --default — НАЗВАНИЕ прошлой плитки; коды 0/1/прочие
# cli: перенос тестов main (выбор, отмена, запасной путь, мёртвый stderr, сбой kdialog → уведомление)
def test_config_error_still_shows_window():   # уведомление config_error, плитки как без файла
@pytest.mark.parametrize("argv, urls", [(["--", "u"], ["u"]), (["u"], ["u"]), (["--list", "u"], ["--list", "u"]), (["--x"], ["--x"])])
def test_options_only_alone(argv, urls):      # --list/--version/--help действуют только единственным аргументом
def test_list_output():                       # строка на плитку: ID, название, команда, значок, через табуляцию
def test_label_for_many_links():              # 3 ссылки → "https://a (+2)"
def test_ctrl_c_ends_the_program():           # SIGINT во время окна — процесс завершён за 1 с
def test_all_modules_loaded_before_window():  # после import cli все модули пакета в sys.modules
def test_zipapp_runs_isolated():              # PYTHONPATH/PYTHONHOME отравлены: --version печатает 0.1.0
def test_zipapp_is_reproducible(); def test_desktop_entry_has_both_languages(); def test_sums_match()
def test_replaced_under_open_window():        # файл заменён через mv, пока окно открыто: выбор доводится до запуска
```

- [ ] **Step 2: Прогнать** — FAIL. **Step 3: Реализовать**. **Step 4: Прогнать весь набор** — PASS. **Commit:** `feat: command line, fallback and single-file build`

### Task 7: Установщик

**Files:** Create: `install.sh`, `tests/containers/{run.sh,check.sh}`; Test: `tests/test_install.py`

**Interfaces — Consumes:** файлы `dist/` из задачи 6. **Produces:** `install.sh [--yes] [--no-default] [--uninstall [--purge]] [--version X]`; переменные `KBC_VERSION`, `KBC_INSTALL_DIR`, `KBC_BASE_URL`, `KBC_TTY` и `KBC_PYTHON` (последние две — для тестов); `previous-defaults` — строки `тип=файл.desktop` для четырёх MIME-типов и `kdeglobals=…`.

- [ ] **Step 1: Написать тесты** (`sh install.sh`, `KBC_BASE_URL=file://…/dist`, подставные `xdg-settings`, `xdg-mime`, `kreadconfig6`, `kwriteconfig6`, `sudo`, менеджеры пакетов)

```python
def test_installs_and_sets_default():         # файл 755, запись с Exec, xdg-settings set, xdg-mime для xhtml
def test_bad_checksum_installs_nothing(); def test_truncated_script_does_nothing()   # обрезанный install.sh
def test_previous_defaults_saved_per_type();  def test_reinstall_keeps_previous_defaults()
def test_uninstall_restores_each_type():      # только те, что всё ещё наши; без прежнего — не трогает
def test_uninstall_keeps_config_unless_purge()
def test_home_with_space():                   # Exec="…/a b/.local/bin/kde-browser-chooser" -- %U
def test_no_xdg_settings():                   # код 0, подсказка, как назначить вручную
@pytest.mark.parametrize("manager, command", [("apt-get", "sudo apt-get install -y python3-pyqt6"),
    ("dnf", "sudo dnf install -y python3-pyqt6"), ("pacman", "sudo pacman -S --needed --noconfirm python-pyqt6"),
    ("zypper", "sudo zypper --non-interactive install python3-PyQt6")])
def test_offers_pyqt6(manager, command):      # ответ «y» → выполнена; «n» → нет
def test_no_pyqt6_no_kdialog_no_default();    def test_no_pyqt6_with_kdialog_defaults_to_no()
def test_no_tty_changes_nothing_without_yes(); def test_root_is_refused(); def test_ostree_prints_rpm_ostree()
def test_old_python_is_refused();             def test_not_kde_warns_and_asks()       # ответ «n» — ничего не поставлено
def test_update_asks_nothing_already_done();  def test_replaces_file_atomically()     # новый inode, старый открыт
```

- [ ] **Step 2: Прогнать** — FAIL. **Step 3: Реализовать**, `shellcheck -s sh install.sh` без замечаний. **Step 4: Прогнать** — PASS.
- [ ] **Step 5: Контейнеры:** `tests/containers/run.sh` для `ubuntu:26.04`, `debian:13`, `fedora:latest`, `archlinux:latest`, `opensuse/tumbleweed:latest`: обычный пользователь с `sudo`, установка с `--yes`, PyQt6 появилась, `--list` отвечает, окно offscreen живёт 3 с без трассировки, `--uninstall`. Имя пакета не подошло → исправить таблицу и тест. Expected: пять раз `OK <образ>`.
- [ ] **Step 6: Commit:** `feat: curl | sh installer`

### Task 8: Стенд KWin, мутации, снимки

**Files:** Create: `tests/kwin/*` (перенос: `nested.sh`, `bus.conf`, `inject.py`, `capture.py`, `messenger.py`, `browser.py`, `fake-browser`, `focus.sh`, `README.md`), `tools/mutate.py`, `docs/images/{window-en,window-ru}.png`

- [ ] **Step 1: Перенести стенд** на настоящий zipapp: подставной браузер задаётся записью `.desktop` во временном `XDG_DATA_HOME`; все `XDG_*`, `WAYLAND_DISPLAY`, `DISPLAY` подменены; шина без `servicedirs`, `prlimit --core=1:1`. Пути — относительно файла, без личных.
- [ ] **Step 2: `tests/kwin/focus.sh`** — Expected: `click: True`, `enter: True`, `control (no chooser): True`; на сборке с вырезанным `request_token` — `click: False` (стенд умеет падать). Новых записей `coredumpctl` — 0. Время до первой отрисовки (медиана 10 запусков): не больше прежнего скрипта + 0,1 с.
- [ ] **Step 3: `tools/mutate.py`** — не меньше 25 поломок по новым модулям (включая все 23 прежние по смыслу). Expected: `survived: 0`.
- [ ] **Step 4: Снимки** окна на английском и русском в масштабе 1,8, только подставные адреса. Посмотреть глазами.
- [ ] **Step 5: Commit:** `test: nested KWin bench and mutation checks`

### Task 9: Документация и CI

**Files:** Create: `README.md`, `README.ru.md`, `CHANGELOG.md`, `CLAUDE.md`, `.github/workflows/{ci,release}.yml`

- [ ] **Step 1: README** (en; ru — перевод, ссылки друг на друга): что это и снимок, установка и удаление, требования, настройка (весь `config.example.toml`), как находятся браузеры, почему нужен токен, ограничения (Plasma 6, X11, Klipper и буфер выделения, двойной щелчок), «если не работает».
- [ ] **Step 2: CLAUDE.md**: команды тестов, сборки, стенда; грабли стенда из дизайна; как выпустить релиз.
- [ ] **Step 3: CI:** job `test` в `ubuntu:26.04` (pytest, shellcheck, сборка), job `install` — `tests/containers/run.sh` по пяти образам. **Release** по тегу `v*`: тесты, `__version__` равна тегу, сборка, `gh release create --notes-from-tag --verify-tag`, как в `graft`.
- [ ] **Step 4: Проверить** команды README в чистом контейнере Ubuntu 26.04, `actionlint` (если есть), повторный полный pytest — PASS. **Commit:** `docs: README, CI and release workflows`

### Task 10: Публикация

- [ ] **Step 1: Проверить историю** на личные данные командой из личного документа. Expected: пусто.
- [ ] **Step 2: Убрать документы:** `git rm -r docs/superpowers`, commit `chore: drop planning documents`.
- [ ] **Step 3: Создать и отправить:** `gh repo create zinin/kde-browser-chooser --public --source . --remote origin`, push `master` и `feat/initial`, PR в `master`.
- [ ] **Step 4: Дождаться** CI и Codex (по правилам автора), исправить замечания, отчитаться. **Слияние — автор.**
- [ ] **Step 5: После слияния и согласия автора:** тег `v0.1.0` → релиз; `curl … | sh` с настоящего релиза в пяти контейнерах. Expected: пять раз `OK`.
- [ ] **Step 6: Перевести машину автора** по личному документу.
