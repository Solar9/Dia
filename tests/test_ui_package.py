import json
import re
from pathlib import Path

from dia.ui import plasmoid_install

STATIC = Path(plasmoid_install.__file__).resolve().parent / "static"


def test_static_files_reference_only_vendored_code() -> None:
    index = (STATIC / "index.html").read_text()
    assert "importmap" in index and "http" not in index.split("importmap")[1].split("</script>")[0]
    assert '<script src="/static/vendor/prism.bundle.js">' in index
    bundle = (STATIC / "vendor" / "prism.bundle.js").read_text()
    assert bundle.startswith("/* Prism 1.29.0") and "gdscript" in bundle.splitlines()[0]
    for module in ("preact.module.js", "hooks.module.js", "htm.module.js"):
        assert (STATIC / "vendor" / module).is_file()
    assert {p.stem for p in (STATIC / "themes").glob("*.css")} == {"dark", "light", "midnight"}


def test_every_theme_defines_the_same_variables() -> None:
    def variables(path: Path) -> set[str]:
        return {
            line.split(":")[0].strip()
            for line in path.read_text().splitlines()
            if line.strip().startswith("--")
        }

    dark = variables(STATIC / "themes" / "dark.css")
    for theme in (STATIC / "themes").glob("*.css"):
        assert variables(theme) == dark, theme.name


def test_ui_strings_exist_in_both_languages() -> None:
    i18n = (STATIC / "js" / "i18n.js").read_text()
    blocks = i18n.split("const STRINGS = {")[1].split("};")[0]
    en, pl = blocks.split("\n  pl: {")

    def keys(block: str) -> set[str]:
        return set(re.findall(r'(\w+): "', block))

    assert keys(en) == keys(pl) and len(keys(en)) > 50


def test_plasmoid_install_fills_in_the_dia_command(tmp_path: Path, monkeypatch) -> None:
    metadata = json.loads((plasmoid_install.PACKAGE / "metadata.json").read_text())
    assert metadata["KPlugin"]["Id"] == plasmoid_install.PLUGIN_ID
    log = tmp_path / "calls"
    fake = tmp_path / "kpackagetool6"
    fake.write_text(
        f'#!/bin/sh\necho "$@" >> {log}\n'
        'case "$*" in *--show*) exit 1;; esac\n'
        f'for a; do [ -d "$a" ] && cp "$a/contents/config/main.xml" {tmp_path}/main.xml; done\n'
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    assert plasmoid_install.install().startswith("installed the Dia widget")
    assert "--install" in log.read_text()
    assert (
        f"<default>{plasmoid_install.dia_command()}</default>"
        in (tmp_path / "main.xml").read_text()
    )


def test_widget_ships_its_icons() -> None:
    images = plasmoid_install.PACKAGE / "contents" / "images"
    qml = (plasmoid_install.PACKAGE / "contents" / "ui" / "main.qml").read_text()
    assert (images / "dia-idle.svg").is_file() and "../images/dia-idle.svg" in qml
    # Lit, Dia's icon is drawn in the theme's accent, like the app draws it.
    assert "root.lit ? root.litIcon" in qml and 'stroke="url(#dia)"' in qml
    assert "audio-input-microphone-muted" not in qml  # Dia's icon, not a microphone
    # Quiet / emergency-stop: local mask SVGs, centred — theme ToolButton icons
    # were blank or off-centre at the foot of the popup.
    for name in ("icon-speaker.svg", "icon-muted.svg", "icon-stop.svg"):
        assert (images / name).is_file() and f"../images/{name}" in qml
    assert "anchors.centerIn: parent" in qml
    # The badge counts decisions only, as the API reports them (dia.core.taskstate).
    assert "waitingCount" in qml and "waiting_for_you" in qml
    assert '"io.github.solar9.dia"' in qml


def test_every_module_import_resolves_to_a_file() -> None:
    modules = [STATIC / "app.js", *(STATIC / "js").rglob("*.js")]
    assert len(modules) > 10
    for module in modules:
        for target in re.findall(r'from "(\.[^"]+)"', module.read_text()):
            assert (module.parent / target).resolve().is_file(), f"{module.name}: {target}"


def test_the_service_worker_precaches_every_app_module() -> None:
    sw = (STATIC / "sw.js").read_text()
    shell = set(re.findall(r'"(/static/[^"]+|/)"', sw.split("const SHELL = [")[1].split("];")[0]))
    modules = {"/static/app.js"} | {
        "/static/" + p.relative_to(STATIC).as_posix() for p in (STATIC / "js").rglob("*.js")
    }
    assert modules <= shell, sorted(modules - shell)
    # nothing is cached that does not exist
    for entry in shell - {"/"}:
        assert (STATIC / entry.removeprefix("/static/")).is_file(), entry


def test_modules_stay_small() -> None:
    assert len((STATIC / "app.js").read_text().splitlines()) <= 300
    for module in (STATIC / "js").rglob("*.js"):
        if module.parent.name == "lang" and module.stem != "index":
            continue  # one string per line: the size of a translation is its key count
        assert len(module.read_text().splitlines()) <= 600, module.name


def test_failed_api_calls_are_not_swallowed():
    # DIA-50: a view that fetches shows the error (js/ui/resource.js) or a toast;
    # `api(...).catch(() => ...)` on one line is the silent pattern.
    silent = re.compile(r"\bapi\(.*\)(\.then\(.*\))?\.catch\(\(\) =>")
    found = [
        f"{path.relative_to(STATIC)}:{n}"
        for path in [STATIC / "app.js", *STATIC.glob("js/**/*.js")]
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if silent.search(line)
    ]
    assert not found, f"silent api() failures: {found}"


def test_resource_component_has_all_three_states():
    source = (STATIC / "js/ui/resource.js").read_text()
    for css in ("state loading", "state error", "state empty"):
        assert css in source
    strings = (STATIC / "js/i18n.js").read_text()
    for key in ("loading", "load_failed", "retry", "nothing_here"):
        assert len(re.findall(rf"(?<!\w){key}:", strings)) == 2, key  # once per language


def test_clients_do_not_count_tasks_themselves():
    # DIA-51: the API's `counts` and `decision` are the only source.
    app = (STATIC / "app.js").read_text()
    assert "status?.counts" in app and "RUNNING.includes" not in app
    tasks_js = (STATIC / "js/views/tasks.js").read_text()
    assert "commit_sha) return" not in tasks_js  # the rule is dia.core.taskstate now
    qml = (STATIC.parent / "plasmoid/contents/ui/main.qml").read_text()
    assert "waiting_for_you" in qml and "t.commit_sha" not in qml


def _string_keys(language: str) -> set[str]:
    i18n = (STATIC / "js" / "i18n.js").read_text()
    blocks = i18n.split("const STRINGS = {")[1].split("\n};")[0]
    en, pl = blocks.split("\n  pl: {")
    return set(re.findall(r"(\w+): \"", en if language == "en" else pl))


def _js_sources() -> list[Path]:
    return [STATIC / "app.js", *(p for p in STATIC.glob("js/**/*.js") if p.name != "i18n.js")]


def test_every_key_the_ui_asks_for_exists_in_both_languages() -> None:
    # DIA-52: t("key") with a missing key would show the key itself.
    used: dict[str, str] = {}
    for path in _js_sources():
        for key in re.findall(r"""\bt\(\s*["']([a-z0-9_]+)["']""", path.read_text()):
            used.setdefault(key, path.name)
    missing = {
        lang: sorted(k for k in used if k not in _string_keys(lang)) for lang in ("en", "pl")
    }
    assert missing == {"en": [], "pl": []}


def test_one_i18n_system_and_no_english_left_in_the_views() -> None:
    for path in _js_sources():
        text = path.read_text()
        # the old per-file helper tr(en, pl) and "pick a string by language" ternaries
        assert not re.search(r"\btr\s*=\s*\(", text), path.name
        assert not re.search(r'lang\s*===\s*"pl"\s*\?\s*"(?!pl-PL)', text), path.name
    # statuses and units are words too
    for key in ("st_done", "st_running", "st_failed", "calls_unit", "minutes_unit"):
        assert key in _string_keys("en") and key in _string_keys("pl")
    tasks = (STATIC / "js/views/tasks.js").read_text()
    assert "<option value=${st}>${st}</option>" not in tasks
    assert ">${label || status}<" not in (STATIC / "js/ui/icons.js").read_text()


def test_every_interface_language_is_complete() -> None:
    # Polish and English live in i18n.js (parity checked above); each extra language in
    # js/lang/ has every key too, uses no key that English lacks, and keeps the placeholders.
    lang_dir = STATIC / "js" / "lang"
    index = (lang_dir / "index.js").read_text()
    codes = sorted(p.stem for p in lang_dir.glob("*.js") if p.stem != "index")
    assert codes == ["de", "es", "fr", "it", "pt"]
    english_text = (STATIC / "js" / "i18n.js").read_text().split("\n  pl: {")[0]
    english = dict(re.findall(r'(\w+): ("(?:[^"\\]|\\.)*")', english_text))
    for code in codes:
        assert f'import {code} from "./{code}.js"' in index
        assert f'{code}: "' in index.split("LANGUAGE_NAMES")[1]  # offered in the selector
        text = (lang_dir / f"{code}.js").read_text()
        translated = dict(re.findall(r'^  (\w+): ("(?:[^"\\]|\\.)*"),$', text, re.M))
        assert set(translated) == set(english), (code, sorted(set(english) ^ set(translated))[:10])
        for key, value in translated.items():
            holes = sorted(re.findall(r"\{\w+\}", value))
            assert holes == sorted(re.findall(r"\{\w+\}", english[key])), (code, key)
    forms = (STATIC / "js/views/settings_forms.js").read_text()
    assert "Object.keys(LANGUAGE_NAMES)" in forms


def test_no_undefined_css_variables() -> None:
    # DIA-55: a var(--x) nobody defines silently falls back to the browser's default.
    defined = set()
    for sheet in [STATIC / "style.css", *(STATIC / "themes").glob("*.css")]:
        defined |= set(re.findall(r"--([\w-]+)\s*:", sheet.read_text()))
    sources = [
        STATIC / "style.css",
        STATIC / "index.html",
        STATIC / "app.js",
        *STATIC.glob("js/**/*.js"),
    ]
    for path in sources:  # layout sizes set from script: style={{ "--list-w": ... }}
        defined |= set(re.findall(r"""["']--([\w-]+)["']\s*:""", path.read_text()))
    used = {}
    for path in sources:
        for name in re.findall(r"var\(--([\w-]+)", path.read_text()):
            used.setdefault(name, path.name)
    assert {k: v for k, v in used.items() if k not in defined} == {}


def test_the_bars_follow_the_theme_and_system_follows_the_os() -> None:
    index = (STATIC / "index.html").read_text()
    assert 'name="theme-color"' in index
    util = (STATIC / "js/util.js").read_text()
    assert "paintThemeColor" in util and 'meta[name="theme-color"]' in util
    assert 'getPropertyValue("--bg")' in util
    # "system" follows prefers-color-scheme and keeps following it
    assert "prefers-color-scheme: light" in util and 'addEventListener?.("change"' in util


def test_the_settings_offer_system_to_the_app_and_phone_only() -> None:
    settings = (STATIC / "js/views/settings.js").read_text()
    assert "system = true" in settings and "system=${false}" in settings
    for code in ("de", "fr", "es", "it", "pt"):
        assert "theme_system:" in (STATIC / f"js/lang/{code}.js").read_text()


def _buttons():
    """(file, line, attributes, text) of every <button>; expressions in the text are "EXPR"."""
    for path in [STATIC / "app.js", *STATIC.glob("js/**/*.js")]:
        source = path.read_text()
        for match in re.finditer(r"<button\b([^<]*?)>(.*?)</button>", source, re.S):
            inner = re.sub(r"<\$\{Icon\}[^>]*/>", "ICON", match.group(2))
            inner = re.sub(r"\$\{[^{}]*(\{[^{}]*\}[^{}]*)*\}", "EXPR", inner).strip()
            line = source[: match.start()].count("\n") + 1
            yield path.name, line, match.group(1), inner


def test_icon_only_buttons_have_an_accessible_name() -> None:
    # DIA-56: a button with an icon or a symbol and no words needs aria-label (or title).
    symbols = {"×", "✎", "✕", "☰", "+", "−", "⋯", "←"}
    bare = []
    for name, line, attrs, inner in _buttons():
        words = re.sub(r"ICON|\s", "", inner)  # "EXPR" counts as words: t("...") or a name
        icon_only = "EXPR" not in words and (words == "" or words in symbols)
        if icon_only and not re.search(r"aria-label|title=", attrs):
            bare.append(f"{name}:{line} {inner!r}")
    assert bare == [], bare


def test_toasts_are_announced_and_rows_are_reachable_by_keyboard() -> None:
    app = (STATIC / "app.js").read_text()
    assert 'class="toasts" aria-live="polite"' in app and 'role=${x.kind === "error"' in app
    # a clickable row is a button (or holds one), never a bare div with onClick
    for path in [STATIC / "app.js", *STATIC.glob("js/**/*.js")]:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            bare = re.search(
                r'<div[^>]*class="[^"]*(session-row|task-row|run-row)[^"]*"[^>]*onClick', line
            )
            if bare:
                assert "session-open" in path.read_text(), f"{path.name}:{number}"
    css = (STATIC / "style.css").read_text()
    assert ".session-row:focus-within .session-actions" in css  # rename/delete by keyboard
    assert ":focus-visible" in css


def test_login_is_a_real_form() -> None:
    # DIA-57: Enter submits, the token is a password field, an empty token is refused.
    login = (STATIC / "js/ui/login.js").read_text()
    assert "<form" in login and "onSubmit=${submit}" in login and 'type="submit"' in login
    assert 'type="password"' in login and "autofocus" in login
    assert 'aria-label=${t("token")}' in login
    assert "if (!token)" in login and 'role="alert"' in login and "token_required" in login
    assert "onClick=${() => onToken(" not in login  # no bare button that skips the check


def test_no_native_dialogs_are_left() -> None:
    # DIA-58: confirm()/prompt()/alert() are replaced by js/ui/dialog.js.
    call = re.compile(r"(?<![\w.$])(confirm|prompt|alert)\(")
    found = [
        f"{path.relative_to(STATIC)}:{number}"
        for path in [STATIC / "app.js", *STATIC.glob("js/**/*.js")]
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if call.search(line) and "Dialog(" not in line
    ]
    assert found == [], found
    dialog = (STATIC / "js/ui/dialog.js").read_text()
    for needle in (
        'role=${item.danger ? "alertdialog" : "dialog"}',
        'aria-modal="true"',
        '"Escape"',
        'e.key !== "Tab"',
    ):
        assert needle in dialog, needle
    assert "dialog-backdrop" in (STATIC / "style.css").read_text()


def test_chat_waits_visibly_takes_several_lines_and_labels_the_plan_buttons() -> None:
    # DIA-60
    chat = (STATIC / "js/views/chat.js").read_text()
    assert 'class="msg dia pending"' in chat and 't("chat_thinking")' in chat
    assert '<textarea ref=${input} class="input chat-text"' in chat
    assert 'e.key === "Enter" && !e.shiftKey && !e.isComposing' in chat  # Shift+Enter: new line
    # the plan buttons say what they do; what Dia is told stays language-independent
    assert 'send("yes", t("plan_yes"))' in chat and 'send("no", t("plan_no"))' in chat
    assert 't("run_plan")' not in chat.split("plan_yes")[0][-400:]
    assert "prefers-reduced-motion" in (STATIC / "style.css").read_text()


def test_the_status_page_starts_with_a_summary_row_of_the_shared_counters() -> None:
    # DIA-63: service, sandbox, agents, running, waiting: one row, using DIA-51's counters.
    status = (STATIC / "js/views/status.js").read_text()
    assert status.index("<${SummaryRow}") < status.index('class="page-jump"')
    summary = (STATIC / "js/views/status_summary.js").read_text()
    for tile in ('"service"', '"sandbox"', '"agents"', '"running"', '"waiting"'):
        assert f"tile({tile}," in summary, tile
    assert "status.counts" in summary and "counts.waiting_for_you" in summary
    for state in ("on", "off", "unavailable"):  # the hint under the sandbox tile
        assert f"sandbox_{state}:" in (STATIC / "js/i18n.js").read_text()
