// Dia for KDE Plasma 6. In the panel: Dia's icon, grey while she is not listening,
// purple while she listens and thinks, pulsing while she speaks; a badge counts what
// waits for your decision. The popup: talk or write to Dia, what waits for you, recent
// tasks, quick actions. Talks to the local API of `dia serve`; the address and the
// token come from `dia ui`.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property string baseUrl: ""
    property string token: ""
    property bool online: false
    property string voice: "idle"
    property string lang: "en"
    property string version: ""
    property bool quiet: false
    property bool halted: false
    property var tasks: []
    property int activeCount: 0
    property int waitingCount: 0     // both counts come from the API (dia.core.taskstate)
    property double nowMs: Date.now()
    property string reply: ""
    property int authFailures: 0   // consecutive 401/403 answers: the token is wrong, not just stale
    property bool asking: false
    property bool confirmStop: false
    property var serviceState: ({})
    property bool serviceBusy: false
    property string serviceResult: ""
    property bool serviceFailed: false
    property string pendingComponent: "dia"
    property string pendingVerb: "stop"

    // The words come from dia.desktop.runtime.STATE_LABELS (the same ones as the tray and the web UI).
    function serviceStatus(component) {
        const unit = serviceState[component];
        if (!unit) return tr("Checking…", "Sprawdzam…");
        const label = unit.label || {};
        return label[root.lang] || label.en || unit.active;
    }

    // Only the verbs that make sense in the unit's state (dia.desktop.runtime.allowed_verbs).
    function canService(component, verb) {
        const unit = serviceState[component];
        return !serviceBusy && !!unit && (unit.actions || []).indexOf(verb) !== -1;
    }

    function verbLabel(verb) {
        const words = (serviceState.words || {}).verbs || {};
        return (words[verb] || {})[root.lang] || verb;
    }

    function controlService(component, verb) {
        if (!canService(component, verb)) return;
        pendingComponent = component;
        pendingVerb = verb;
        if (verb === "start") executeService();
        else {
            root.expanded = true;
            Qt.callLater(() => serviceConfirm.open());
        }
    }

    function executeService() {
        serviceBusy = true;
        dia("runtime " + pendingVerb + " " + pendingComponent);
    }

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: root.tr("Open Dia", "Otwórz Dia")
            icon.name: "io.github.solar9.dia"
            onTriggered: root.openApp()
        },
        PlasmaCore.Action {
            text: root.tr("Widget panel", "Panel widgetu")
            onTriggered: root.expanded = !root.expanded
        },
        PlasmaCore.Action {
            text: root.tr("Start Dia", "Uruchom Dia")
            enabled: root.canService("dia", "start")
            onTriggered: root.controlService("dia", "start")
        },
        PlasmaCore.Action {
            text: root.tr("Stop Dia", "Zatrzymaj Dia")
            enabled: root.canService("dia", "stop")
            onTriggered: root.controlService("dia", "stop")
        },
        PlasmaCore.Action {
            text: root.tr("Restart Dia", "Uruchom Dia ponownie")
            enabled: root.canService("dia", "restart")
            onTriggered: root.controlService("dia", "restart")
        },
        PlasmaCore.Action {
            text: root.tr("Start Ollama", "Uruchom Ollamę")
            enabled: root.canService("ollama", "start")
            onTriggered: root.controlService("ollama", "start")
        },
        PlasmaCore.Action {
            text: root.tr("Stop Ollama", "Zatrzymaj Ollamę")
            enabled: root.canService("ollama", "stop")
            onTriggered: root.controlService("ollama", "stop")
        },
        PlasmaCore.Action {
            text: root.tr("Restart Ollama", "Uruchom Ollamę ponownie")
            enabled: root.canService("ollama", "restart")
            onTriggered: root.controlService("ollama", "restart")
        },
        PlasmaCore.Action {
            text: root.tr("Settings", "Ustawienia")
            icon.name: "configure"
            onTriggered: root.openApp("settings")
        }
    ]

    readonly property bool speaking: voice === "speaking"
    readonly property bool lit: voice !== "idle"   // listening, thinking or speaking
    // What needs your decision: changes to merge or discard, plans to approve. A finished
    // read-only task (an answer, no changes) needs none.
    readonly property var waiting: tasks.filter((t) => !!t.decision)

    function tr(en, pl) { return root.lang === "pl" ? pl : en; }

    // "4m", "1h 05m": how long a task has been running (created_at → now).
    function elapsed(iso) {
        const seconds = Math.max(0, Math.floor((nowMs - new Date(iso).getTime()) / 1000));
        if (seconds < 60) return seconds + "s";
        if (seconds < 3600) return Math.floor(seconds / 60) + "m";
        const minutes = Math.floor(seconds / 60) % 60;
        return Math.floor(seconds / 3600) + "h " + (minutes < 10 ? "0" : "") + minutes + "m";
    }

    function taskStatus(task) {
        return task.status === "done" && !task.commit_sha ? root.tr("finished", "zakończone") : statusText(task.status);
    }

    function statusText(status) {
        const pl = { done: "gotowe do decyzji", planned: "plan do zatwierdzenia", running: "w toku",
            queued: "w kolejce", waiting: "czeka na limit", failed: "nieudane", merged: "scalone",
            discarded: "odrzucone", published: "opublikowane", cancelled: "anulowane" };
        const en = { done: "ready for your decision", planned: "plan to approve", waiting: "waiting for a limit" };
        return (root.lang === "pl" ? pl[status] : en[status]) || status;
    }

    // Dia's theme for the widget (Settings → Look: the app's, or its own): its colours
    // come with Dia's status. Until then, and without Dia, the default "dark" theme.
    readonly property var defaultColors: ({
        bg: "#131317", card: "#18181d", hover: "#1f1f25", active: "#2a2538", border: "#26262d",
        borderStrong: "#33333b", text: "#ececf1", muted: "#a1a1aa", faint: "#8a8a94",
        accent: "#b4a2ff", accentInk: "#c9b8ff", onAccent: "#17131f", ok: "#7ad9a6",
        warn: "#f2b55a", danger: "#f0868a", info: "#8cc4ff"
    })
    property var c: defaultColors

    function applyTheme(colors) {
        if (!colors || !colors.bg) return;
        const names = { bg: "bg", card: "bg-elevated", hover: "bg-hover", active: "accent-soft",
            border: "border", borderStrong: "border-strong", text: "text", muted: "text-muted",
            faint: "text-faint", accent: "accent", accentInk: "accent-ink", onAccent: "accent-text",
            ok: "ok", warn: "warn", danger: "danger", info: "info" };
        const next = {};
        for (const key in names) next[key] = colors[names[key]] || defaultColors[key];
        if (JSON.stringify(next) !== JSON.stringify(root.c)) root.c = next;
    }

    // Dia's icon in the theme's accent: the rings of dia.svg, the gradient from lighter
    // to darkest, as the app draws it (grey dia-idle.svg while she is not listening).
    readonly property string litIcon: {
        const rgb = [1, 3, 5].map((i) => parseInt(c.accent.slice(-6).substr(i - 1, 2), 16));
        const mix = (share, other) => "#" + rgb.map((v) => Math.round(v * share + other * (1 - share))
            .toString(16).padStart(2, "0")).join("");
        const stops = [[0, mix(0.45, 255)], [0.46, mix(1, 0)], [0.72, mix(0.7, 0)], [1, mix(0.35, 0)]]
            .map((stop) => '<stop offset="' + stop[0] + '" stop-color="' + stop[1] + '"/>').join("");
        const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs>'
            + '<linearGradient id="dia" x1="0" y1="0" x2="1" y2="1">' + stops + '</linearGradient></defs>'
            + '<circle cx="256" cy="256" r="208" fill="none" stroke="url(#dia)" stroke-width="54"/>'
            + '<circle cx="256" cy="256" r="112" fill="url(#dia)"/></svg>';
        return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
    }

    readonly property var statusColor: ({
        "done": c.ok, "merged": c.ok, "failed": c.danger, "running": c.warn,
        "queued": c.warn, "waiting": c.warn, "planned": c.info, "published": c.info
    })

    readonly property var running: tasks.filter((t) => ["running", "queued", "waiting"].indexOf(t.status) !== -1)

    // "io.github.solar9.dia", not "dia": icon themes ship the Dia diagram editor's icon as "dia".
    Plasmoid.icon: "io.github.solar9.dia"
    toolTipMainText: "Dia" + (version ? " " + version : "")
    toolTipSubText: !online ? "Dia: " + serviceStatus("dia") + " · Ollama: " + serviceStatus("ollama")
        : voice === "listening" ? tr("Listening…", "Słucham…")
        : voice === "processing" ? tr("Thinking…", "Myślę…")
        : speaking ? tr("Speaking…", "Mówię…")
        : waitingCount > 0 ? tr("%1 waiting for you", "Czeka na Ciebie: %1").arg(waitingCount)
        : activeCount > 0 ? tr("%1 running", "W toku: %1").arg(activeCount)
        : tr("Ready", "Gotowa")

    // Runs `dia ...` commands: the UI address and token (`dia ui`), opening the app.
    P5Support.DataSource {
        id: shell
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            const out = (data["stdout"] || "").trim();
            if (source.indexOf(" runtime ") !== -1) {
                const isStatus = source.endsWith(" runtime status");
                if (!isStatus) root.serviceBusy = false;
                try {
                    const result = JSON.parse(out);
                    const who = root.pendingComponent === "dia" ? "Dia" : "Ollama";
                    if (result.error) {
                        root.reply = result.error;
                        if (!isStatus) {
                            root.serviceFailed = true;
                            root.expanded = true;
                            root.serviceResult = who + ": " + root.verbLabel(root.pendingVerb) + " · "
                                + root.tr("Failed", "Nie udało się") + ": " + result.error;
                        }
                    } else {
                        if (!isStatus) root.serviceFailed = false;
                        if (!isStatus) root.serviceResult = who + ": " + root.verbLabel(root.pendingVerb) + " · "
                            + root.tr("Done", "Gotowe");
                        root.serviceState = result;
                        root.lang = result.language || root.lang;
                        if (!isStatus) root.refresh();
                    }
                } catch (error) {
                    root.reply = (data["stderr"] || out || String(error)).trim();
                }
                disconnectSource(source);
                return;
            }
            const match = out.match(/(http:\/\/\S+?\/)#token=(\S+)/);
            if (match) {
                root.baseUrl = match[1];
                root.token = match[2];
                root.refresh();
            }
            disconnectSource(source);
        }
    }

    function dia(args) {
        shell.connectSource(Plasmoid.configuration.diaCommand + " " + args);
    }

    function openApp(view, task) {
        dia("app" + (view ? " --view " + view : "") + (task ? " --task " + task : ""));
        root.expanded = false;
    }

    function request(method, path, body, onResult, onError) {
        const xhr = new XMLHttpRequest();
        xhr.onreadystatechange = () => {
            if (xhr.readyState !== XMLHttpRequest.DONE) return;
            if (path === "api/status") {
                root.online = xhr.status === 200;
                if (!root.online) { root.voice = "idle"; root.tasks = []; root.activeCount = 0; root.waitingCount = 0; }
            }
            if (xhr.status >= 200 && xhr.status < 300) {
                root.authFailures = 0;
                if (onResult) onResult(xhr.responseText ? JSON.parse(xhr.responseText) : null);
            } else if (xhr.status === 401 || xhr.status === 403) {
                root.token = "";  // a new token (Dia reinstalled): ask `dia ui` again
                root.authFailures += 1;
                // The second refusal in a row: a fresh token did not help, so say what to do
                if (root.authFailures >= 2) root.reply = root.tr(
                    "Dia refused the widget's token. Run `dia ui` once, or pair the widget again (Settings → Devices).",
                    "Dia odrzuciła token widgetu. Uruchom raz `dia ui` albo sparuj widget ponownie (Ustawienia → Urządzenia).");
            } else if (onError) {
                onError(xhr.status ? xhr.responseText || ("HTTP " + xhr.status) : root.tr("Dia is not running", "Dia nie działa"));
            }
        };
        xhr.open(method, root.baseUrl + path);
        xhr.setRequestHeader("Authorization", "Bearer " + root.token);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.send(body ? JSON.stringify(body) : null);
    }

    function refresh() {
        if (!root.token) { dia("ui"); return; }
        request("GET", "api/status", null, (status) => {
            root.voice = status.voice || "idle";
            root.activeCount = (status.counts || {}).running || 0;
            root.waitingCount = (status.counts || {}).waiting_for_you || 0;
            root.nowMs = Date.now();
            root.lang = status.language || "en";
            root.version = status.version || "";
            root.quiet = !!status.quiet;
            root.halted = !!status.halted;
            // the widget's own theme, or the app's (Settings → Look)
            root.applyTheme(status.widget_theme_colors || status.theme_colors);
        });
        request("GET", "api/tasks?limit=20", null, (tasks) => root.tasks = tasks);
    }

    function post(path, body) {
        request("POST", path, body || {}, () => root.refresh(), (error) => root.reply = error);
    }

    function talk() { if (root.online) post("api/voice/toggle"); }

    // True when the request went out: an empty or blank prompt is never sent.
    function send(text) {
        if (!text.trim() || root.asking) return false;
        root.asking = true;
        root.reply = "";
        request("POST", "api/chat", { text: text }, (answer) => {
            root.asking = false;
            root.reply = answer.reply || root.tr("Done.", "Zrobione.");
            root.refresh();
        }, (error) => { root.asking = false; root.reply = error; });
        return true;
    }

    Timer {
        // Open: quicker while the voice is busy, so the icon follows listening/speaking.
        // Closed: only a slow look, so the badge on the panel icon stays true.
        interval: !root.expanded ? 30000 : root.voice === "idle" ? 4000 : 700
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    Timer {
        id: stopTimeout
        interval: 4000
        onTriggered: root.confirmStop = false
    }

    Timer {  // the services' state is only drawn in the popup (and the tooltip while Dia is down)
        interval: root.expanded ? 4000 : 30000
        running: root.expanded || !root.online
        repeat: true
        triggeredOnStart: true
        onTriggered: root.dia("runtime status")
    }

    // Use the property, not the injected signal parameter (Plasma/Qt deprecation).
    onExpandedChanged: if (root.expanded) { root.refresh(); root.dia("runtime status"); }

    compactRepresentation: MouseArea {
        id: compact
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: (mouse) => {
            // Left click brings up the widget's popup; the app is one button inside it
            // and in the context menu.
            if (mouse.button === Qt.MiddleButton) root.talk();
            else root.expanded = !root.expanded;
        }

        Image {
            id: logo
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height) * 0.86
            height: width
            sourceSize: Qt.size(width * 2, height * 2)
            source: root.lit ? root.litIcon : "../images/dia-idle.svg"
            opacity: root.online ? 1 : 0.45
            smooth: true

            SequentialAnimation {
                id: pulse  // speaking: Dia's icon beats
                running: root.speaking
                loops: Animation.Infinite
                NumberAnimation { target: logo; property: "scale"; to: 1.16; duration: 420; easing.type: Easing.InOutQuad }
                NumberAnimation { target: logo; property: "scale"; to: 0.88; duration: 420; easing.type: Easing.InOutQuad }
                onRunningChanged: if (!running) logo.scale = 1
            }
            SequentialAnimation {
                id: thinking  // thinking: a slow breath
                running: root.voice === "processing"
                loops: Animation.Infinite
                NumberAnimation { target: logo; property: "opacity"; to: 0.55; duration: 700 }
                NumberAnimation { target: logo; property: "opacity"; to: 1; duration: 700 }
                onRunningChanged: if (!running) logo.opacity = Qt.binding(() => root.online ? 1 : 0.45)
            }
        }

        Rectangle {  // how many things wait for your decision
            visible: root.waitingCount > 0
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: Math.max(height, badge.implicitWidth + 4)
            height: Math.round(parent.height * 0.42)
            radius: height / 2
            color: root.c.accent
            PlasmaComponents.Label {
                id: badge
                anchors.centerIn: parent
                text: root.waitingCount
                color: root.c.onAccent
                font.pixelSize: parent.height * 0.75
                font.bold: true
            }
        }
    }

    // The popup, like the app's Inbox: services, talk or write to Dia, what waits for
    // your decision, what runs now, and the app's views.
    fullRepresentation: Rectangle {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 24
        Layout.preferredHeight: Kirigami.Units.gridUnit * 38
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        color: root.c.bg
        radius: 10

        QQC2.Dialog {
            id: serviceConfirm
            title: root.tr("Confirm service action", "Potwierdź zmianę usług")
            modal: true
            width: parent.width - 40
            x: 20
            y: (parent.height - height) / 2
            standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
            onAccepted: root.executeService()
            contentItem: PlasmaComponents.Label {
                text: (root.pendingComponent === "dia" ? "Dia" : "Ollama") + ": " + root.verbLabel(root.pendingVerb) + "\n"
                    + root.tr("Active tasks may be interrupted. Continue?", "Aktywne zadania mogą zostać przerwane. Kontynuować?")
                wrapMode: Text.Wrap
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 12

            StatusHeader { panel: root }

            Controls { panel: root }

            TaskList { panel: root }

            // ---- the app's views and quick switches
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: root.c.border }
            RowLayout {
                Layout.fillWidth: true
                spacing: 2
                Repeater {
                    model: [
                        { view: "inbox", icon: "mail-folder-inbox", label: root.tr("Inbox", "Skrzynka") },
                        { view: "tasks", icon: "view-list-details", label: root.tr("Tasks", "Zadania") },
                        { view: "chat", icon: "dialog-messages", label: root.tr("Chat", "Czat") },
                        { view: "status", icon: "view-statistics", label: root.tr("Status", "Status") },
                        { view: "settings", icon: "configure", label: root.tr("Settings", "Ustawienia") }
                    ]
                    delegate: QQC2.ToolButton {
                        required property var modelData
                        icon.name: modelData.icon
                        icon.color: root.c.muted
                        text: modelData.label
                        display: QQC2.AbstractButton.IconOnly
                        implicitWidth: 36; implicitHeight: 36
                        onClicked: root.openApp(modelData.view, "")
                        QQC2.ToolTip.visible: hovered
                        QQC2.ToolTip.text: text
                        background: Rectangle { radius: 8; color: parent.hovered ? root.c.hover : "transparent" }
                    }
                }
                Item { Layout.fillWidth: true }
                QQC2.ToolButton {
                    id: quietBtn
                    text: root.quiet ? root.tr("Quiet mode: on", "Tryb cichy: włączony")
                        : root.tr("Quiet mode: off", "Tryb cichy: wyłączony")
                    Accessible.name: text
                    checkable: true
                    checked: root.quiet
                    enabled: root.online
                    padding: 0
                    implicitWidth: 36
                    implicitHeight: 36
                    onClicked: root.post("api/quiet", { on: !root.quiet })
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: text
                    // Own SVGs + centered contentItem: theme icons via icon.name often
                    // render blank here, and a loose RowLayout leaves Stop off-centre.
                    contentItem: Item {
                        Kirigami.Icon {
                            anchors.centerIn: parent
                            width: 18
                            height: 18
                            source: Qt.resolvedUrl(root.quiet ? "../images/icon-muted.svg" : "../images/icon-speaker.svg")
                            isMask: true
                            color: root.quiet ? root.c.accentInk : root.c.muted
                        }
                    }
                    background: Rectangle {
                        radius: 8
                        color: quietBtn.checked ? root.c.active : quietBtn.hovered ? root.c.hover : "transparent"
                    }
                }
                QQC2.ToolButton {  // two clicks: an emergency stop is not a misclick
                    id: stopBtn
                    text: root.confirmStop ? root.tr("Click again to stop every agent", "Kliknij jeszcze raz, by zatrzymać wszystkich agentów")
                        : root.tr("Emergency stop", "Zatrzymanie awaryjne")
                    Accessible.name: text
                    visible: !root.halted
                    enabled: root.online
                    padding: 0
                    implicitHeight: 36
                    implicitWidth: root.confirmStop ? Math.max(36, stopRow.implicitWidth + 20) : 36
                    onClicked: {
                        if (root.confirmStop) { root.confirmStop = false; root.post("api/stop"); }
                        else { root.confirmStop = true; stopTimeout.restart(); }
                    }
                    QQC2.ToolTip.visible: hovered && !root.confirmStop
                    QQC2.ToolTip.text: text
                    contentItem: Item {
                        RowLayout {
                            id: stopRow
                            anchors.centerIn: parent
                            spacing: 6
                            Kirigami.Icon {
                                source: Qt.resolvedUrl("../images/icon-stop.svg")
                                isMask: true
                                color: root.c.danger
                                Layout.preferredWidth: 16
                                Layout.preferredHeight: 16
                            }
                            QQC2.Label {
                                visible: root.confirmStop
                                text: stopBtn.text
                                color: root.c.danger
                                font.pixelSize: 12
                            }
                        }
                    }
                    background: Rectangle {
                        radius: 8
                        color: root.confirmStop ? Qt.rgba(0.94, 0.53, 0.54, 0.12)
                             : stopBtn.hovered ? root.c.hover : "transparent"
                        border.color: root.confirmStop ? Qt.rgba(0.94, 0.53, 0.54, 0.4) : "transparent"
                    }
                }
            }
        }
    }

}
