"""The widget's QML files: balanced, and the extracted components load and bind
against a mock panel (QtQml only; Plasma's own modules are not needed for them)."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from dia.ui import plasmoid_install

UI = plasmoid_install.PACKAGE / "contents" / "ui"
COMPONENTS = ("StatusHeader", "Controls", "TaskList", "WaitingCard", "TaskRow")


def test_every_qml_file_is_balanced_and_main_uses_the_components() -> None:
    for path in UI.glob("*.qml"):
        text = path.read_text()
        for open_, close in ("{}", "()", "[]"):
            assert text.count(open_) == text.count(close), f"{path.name}: {open_}"
    main = (UI / "main.qml").read_text()
    for name in ("StatusHeader", "Controls", "TaskList"):
        assert f"{name} {{ panel: root }}" in main and (UI / f"{name}.qml").is_file()
    assert (UI / "WaitingCard.qml").is_file() and (UI / "TaskRow.qml").is_file()


def mock_panel(files: list[Path], reply: str = '"hello"') -> str:
    props, funcs, colors = set(), set(), set()
    for path in files:
        text = path.read_text()
        for m in re.finditer(r"\b(?:part|card|row|list)\.panel\.(\w+)(\()?", text):
            (funcs if m.group(2) else props).add(m.group(1))
        colors |= set(re.findall(r"panel\.c\.(\w+)", text))
    props -= funcs | {"c"}
    values = {
        "waiting": '[{id: "t1", status: "done", commit_sha: "x", project: "demo", agent: "a",'
        ' prompt: "Add\\nmore", diffstat: {added: 2, removed: 1}},'
        ' {id: "t2", status: "planned", project: "demo", agent: "a", prompt: "Plan"}]',
        "running": '[{id: "t3", status: "running", project: "demo", agent: "a", prompt: "Run"}]',
        "serviceState": "({})",
        "statusColor": "({})",
        "online": "true",
        "halted": "true",
        "reply": reply,
        "version": '"0.1.2"',
        "litIcon": '""',
    }
    lines = [f"    property var {p}: {values.get(p, 'null')}" for p in sorted(props)]
    lines += [f"    function {f}() {{ return ''; }}" for f in sorted(funcs - {"tr"})]
    colour_map = ", ".join(f"{c}: 'red'" for c in sorted(colors))
    return (
        "import QtQuick\nItem {\n"
        f"    property var c: ({{{colour_map}}})\n" + "\n".join(lines) + "\n"
        "    function tr(en, pl) { return en; }\n}\n"
    )


def load_components(
    tmp_path: Path, reply: str = '"hello"', probe: str = ""
) -> subprocess.CompletedProcess:
    """Load the components against the mock panel; ``probe`` is Python run on the created item."""
    pytest.importorskip("PySide6.QtQml")
    tmp_path.mkdir(parents=True, exist_ok=True)

    files = [UI / f"{name}.qml" for name in COMPONENTS]
    for path in files:
        (tmp_path / path.name).write_text(path.read_text())
    (tmp_path / "Mock.qml").write_text(mock_panel(files, reply))
    # A stand-in for Kirigami (not installed everywhere).
    kirigami = tmp_path / "org" / "kde" / "kirigami"
    kirigami.mkdir(parents=True)
    (kirigami / "qmldir").write_text(
        "module org.kde.kirigami\nIcon 1.0 Icon.qml\nsingleton Units 1.0 Units.qml\n"
    )
    (kirigami / "Icon.qml").write_text(
        "import QtQuick\nItem { property var source; property var color; property bool isMask }\n"
    )
    (kirigami / "Units.qml").write_text(
        "pragma Singleton\nimport QtQuick\nQtObject { property int gridUnit: 18 }\n"
    )
    (tmp_path / "Test.qml").write_text(
        "import QtQuick\nimport QtQuick.Layouts\nItem {\n    width: 420; height: 900\n"
        "    Mock { id: panel }\n    ColumnLayout {\n        anchors.fill: parent\n"
        "        StatusHeader { panel: panel }\n        Controls { panel: panel }\n"
        "        TaskList { panel: panel }\n    }\n}\n"
    )
    script = (
        "import sys\n"
        "from PySide6.QtCore import QTimer, QUrl\n"
        "from PySide6.QtGui import QGuiApplication\n"
        "from PySide6.QtQml import QQmlComponent, QQmlEngine\n"
        "app = QGuiApplication([])\n"
        "engine = QQmlEngine()\n"
        "engine.addImportPath(sys.argv[1])\n"
        "warnings = []\n"
        "engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))\n"
        "component = QQmlComponent(engine, QUrl.fromLocalFile(sys.argv[1] + '/Test.qml'))\n"
        "item = component.create()\n"
        "errors = [e.toString() for e in component.errors()]\n"
        "QTimer.singleShot(300, app.quit)\n"
        "app.exec()\n"
        "print('ERRORS', errors)\n"
        # The icon is found relative to the real package, not this temporary folder.
        "print('WARNINGS', [w for w in warnings if 'dia-idle.svg' not in w])\n"
        "print('CREATED', item is not None)\n" + probe
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        timeout=60,
    )
    if "ImportError" in result.stderr:  # e.g. libEGL missing on a bare CI runner
        pytest.skip(result.stderr.strip().splitlines()[-1])
    assert "ERRORS []" in result.stdout, result.stdout + result.stderr
    assert "WARNINGS []" in result.stdout, result.stdout
    assert "CREATED True" in result.stdout
    return result


def test_extracted_components_load_and_bind(tmp_path: Path) -> None:
    load_components(tmp_path)


def test_a_long_answer_scrolls_in_a_box_of_limited_height(tmp_path: Path) -> None:
    """DIA-59: it neither grows the popup nor is cut off with an ellipsis."""
    long_reply = '"' + "".join(f"line {i}\\n\\n" for i in range(80)) + '"'  # Markdown paragraphs
    probe = (
        "from PySide6.QtCore import QObject\n"
        "box = item.findChild(QObject, 'answerBox')\n"
        "label = item.findChild(QObject, 'answer')\n"
        "print('BOX', box.property('height') <= 160, label.property('implicitHeight') > 160,\n"
        "      'line 79' in label.property('text'))\n"
    )
    result = load_components(tmp_path / "long", long_reply, probe)
    assert "BOX True True True" in result.stdout, result.stdout
    short = load_components(tmp_path / "short", '"hello"', probe)
    assert "BOX True False False" in short.stdout, short.stdout  # a short answer is not boxed in


def test_the_widget_polls_slowly_when_closed_and_says_what_a_refused_token_needs() -> None:
    main = (UI / "main.qml").read_text()
    # DIA-59: no fast polling while collapsed; the services' timer stops unless Dia is down
    assert 'interval: !root.expanded ? 30000 : root.voice === "idle" ? 4000 : 700' in main
    assert "running: root.expanded || !root.online" in main
    assert "onExpandedChanged: if (root.expanded) { root.refresh(); root.dia(" in main
    # 401: the second refusal in a row tells the person what to do (pair again / the token)
    assert "root.authFailures >= 2" in main and "pair the widget again" in main
    assert "root.authFailures = 0;" in main
    # an empty or blank prompt is never sent, and its box is not cleared as if it were
    assert "if (!text.trim() || root.asking) return false;" in main
    controls = (UI / "Controls.qml").read_text()
    assert controls.count("if (part.panel.send(") == 2
    assert "maximumLineCount" not in controls and "QQC2.ScrollView" in controls
