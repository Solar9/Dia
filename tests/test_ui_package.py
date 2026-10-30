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
    app = (STATIC / "app.js").read_text()
    blocks = app.split("const STRINGS = {")[1].split("};")[0]
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


def test_qml_parses_as_far_as_brackets_go() -> None:
    qml = (plasmoid_install.PACKAGE / "contents" / "ui" / "main.qml").read_text()
    for open_, close in ("{}", "()", "[]"):
        assert qml.count(open_) == qml.count(close), open_


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
    # The badge counts decisions only: changes to merge (a commit) and plans.
    assert '(t.status === "done" && t.commit_sha) || t.status === "planned"' in qml
    assert '"io.github.solar9.dia"' in qml
