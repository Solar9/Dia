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
    property string reply: ""
    property bool asking: false
    property bool confirmStop: false
    property var serviceState: ({})
    property bool serviceBusy: false
    property string pendingComponent: "dia"
    property string pendingVerb: "stop"

    function serviceStatus(component) {
        const unit = serviceState[component];
        if (!unit) return tr("Checking…", "Sprawdzam…");
        const labels = { active: tr("Running", "Działa"), inactive: tr("Stopped", "Zatrzymana"),
            failed: tr("Error", "Błąd"), activating: tr("Starting…", "Uruchamia się…"),
            deactivating: tr("Stopping…", "Zatrzymuje się…") };
        return unit.load === "not-found" ? tr("Not installed", "Nie zainstalowano") : (labels[unit.active] || unit.active);
    }

    function controlService(component, verb) {
        if (serviceBusy) return;
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
            enabled: !root.serviceBusy
            onTriggered: root.controlService("dia", "start")
        },
        PlasmaCore.Action {
            text: root.tr("Stop Dia", "Zatrzymaj Dia")
            enabled: !root.serviceBusy
            onTriggered: root.controlService("dia", "stop")
        },
        PlasmaCore.Action {
            text: root.tr("Restart Dia", "Uruchom Dia ponownie")
            enabled: !root.serviceBusy
            onTriggered: root.controlService("dia", "restart")
        },
        PlasmaCore.Action {
            text: root.tr("Start Ollama", "Uruchom Ollamę")
            enabled: !root.serviceBusy
            onTriggered: root.controlService("ollama", "start")
        },
        PlasmaCore.Action {
            text: root.tr("Stop Ollama", "Zatrzymaj Ollamę")
            enabled: !root.serviceBusy
            onTriggered: root.controlService("ollama", "stop")
        },
        PlasmaCore.Action {
            text: root.tr("Restart Ollama", "Uruchom Ollamę ponownie")
            enabled: !root.serviceBusy
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
    readonly property var waiting: tasks.filter((t) => (t.status === "done" && t.commit_sha) || t.status === "planned")

    function tr(en, pl) { return root.lang === "pl" ? pl : en; }

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
        : waiting.length > 0 ? tr("%1 waiting for you", "Czeka na Ciebie: %1").arg(waiting.length)
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
                    if (result.error) {
                        root.reply = result.error;
                        if (!isStatus) root.expanded = true;
                    } else {
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
                if (!root.online) { root.voice = "idle"; root.tasks = []; root.activeCount = 0; }
            }
            if (xhr.status >= 200 && xhr.status < 300) {
                if (onResult) onResult(xhr.responseText ? JSON.parse(xhr.responseText) : null);
            } else if (xhr.status === 401 || xhr.status === 403) {
                root.token = "";  // a new token (Dia reinstalled): ask `dia ui` again
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
            root.activeCount = (status.active || []).length;
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

    function send(text) {
        if (!text.trim() || root.asking) return;
        root.asking = true;
        root.reply = "";
        request("POST", "api/chat", { text: text }, (answer) => {
            root.asking = false;
            root.reply = answer.reply || root.tr("Done.", "Zrobione.");
            root.refresh();
        }, (error) => { root.asking = false; root.reply = error; });
    }

    Timer {
        // Quicker while the voice is busy, so the icon follows listening/speaking.
        interval: root.voice === "idle" ? 4000 : 700
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

    Timer {
        interval: 4000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.dia("runtime status")
    }

    // Use the property, not the injected signal parameter (Plasma/Qt deprecation).
    onExpandedChanged: if (root.expanded) root.refresh()

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
            visible: root.waiting.length > 0
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            width: Math.max(height, badge.implicitWidth + 4)
            height: Math.round(parent.height * 0.42)
            radius: height / 2
            color: root.c.accent
            PlasmaComponents.Label {
                id: badge
                anchors.centerIn: parent
                text: root.waiting.length
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
                text: root.pendingComponent + ": " + root.pendingVerb + "\n"
                    + root.tr("Active tasks may be interrupted. Continue?", "Aktywne zadania mogą zostać przerwane. Kontynuować?")
                wrapMode: Text.Wrap
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 12

            // ---- header: Dia, the connection, the app
            RowLayout {
                spacing: 8
                Image {
                    source: root.lit ? root.litIcon : "../images/dia-idle.svg"
                    sourceSize: Qt.size(48, 48)
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                }
                QQC2.Label { text: "dia"; color: root.c.text; font.pixelSize: 20; font.weight: Font.ExtraBold }
                QQC2.Label { text: root.version; color: root.c.faint; font.family: "monospace"; font.pixelSize: 11 }
                Item { Layout.fillWidth: true }
                Rectangle {
                    radius: 5
                    color: root.online ? Qt.rgba(0.48, 0.85, 0.65, 0.12) : root.c.card
                    implicitWidth: connLabel.implicitWidth + 24
                    implicitHeight: 24
                    Rectangle {
                        width: 6; height: 6; radius: 3
                        anchors.left: parent.left; anchors.leftMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        color: root.online ? root.c.ok : root.c.faint
                    }
                    QQC2.Label {
                        id: connLabel
                        anchors.left: parent.left; anchors.leftMargin: 18
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.online ? (root.activeCount > 0 ? root.tr("%1 running", "w toku: %1").arg(root.activeCount)
                            : root.tr("Connected", "Połączono")) : root.tr("Not running", "Nie działa")
                        color: root.online ? root.c.ok : root.c.muted
                        font.pixelSize: 11
                    }
                }
                QQC2.ToolButton {
                    icon.name: "window-new"
                    icon.color: root.c.muted
                    text: root.tr("Open Dia", "Otwórz Dia")
                    display: QQC2.AbstractButton.IconOnly
                    onClicked: root.openApp("", "")
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: text
                    background: Rectangle { radius: 8; color: parent.hovered ? root.c.hover : "transparent" }
                }
            }

            // ---- services: Dia and Ollama
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: services.implicitHeight + 16
                radius: 10
                color: root.c.card
                border.color: root.c.border
                ColumnLayout {
                    id: services
                    anchors.fill: parent
                    anchors.margins: 8
                    anchors.leftMargin: 12
                    spacing: 2
                    Repeater {
                        model: ["dia", "ollama"]
                        delegate: RowLayout {
                            required property string modelData
                            readonly property string unit: (root.serviceState[modelData] || {}).active || ""
                            spacing: 6
                            Rectangle {
                                Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4
                                color: unit === "active" ? root.c.ok : unit === "failed" ? root.c.danger
                                    : unit === "activating" || unit === "deactivating" ? root.c.warn : root.c.faint
                            }
                            QQC2.Label { text: modelData === "dia" ? "Dia" : "Ollama"; color: root.c.text }
                            QQC2.Label {
                                Layout.fillWidth: true
                                text: root.serviceStatus(modelData)
                                color: root.c.muted
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            Repeater {
                                model: [
                                    { verb: "start", icon: "media-playback-start", label: root.tr("Start", "Uruchom") },
                                    { verb: "stop", icon: "media-playback-stop", label: root.tr("Stop", "Zatrzymaj") },
                                    { verb: "restart", icon: "view-refresh", label: root.tr("Restart", "Uruchom ponownie") }
                                ]
                                delegate: QQC2.ToolButton {
                                    required property var modelData
                                    icon.name: modelData.icon
                                    icon.color: root.c.muted
                                    icon.width: 16; icon.height: 16
                                    text: modelData.label
                                    display: QQC2.AbstractButton.IconOnly
                                    enabled: !root.serviceBusy
                                    implicitWidth: 30; implicitHeight: 30
                                    onClicked: root.controlService(parent.modelData, modelData.verb)
                                    QQC2.ToolTip.visible: hovered
                                    QQC2.ToolTip.text: text
                                    background: Rectangle { radius: 6; color: parent.hovered ? root.c.hover : "transparent" }
                                }
                            }
                        }
                    }
                }
            }

            // ---- emergency stop in force
            Rectangle {
                Layout.fillWidth: true
                visible: root.halted
                implicitHeight: 44
                radius: 10
                color: Qt.rgba(0.94, 0.53, 0.54, 0.10)
                border.color: Qt.rgba(0.94, 0.53, 0.54, 0.35)
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 6
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: root.tr("Emergency stop: no agent runs.", "Zatrzymanie awaryjne: żaden agent nie działa.")
                        color: root.c.danger
                        wrapMode: Text.Wrap
                    }
                    QQC2.Button {
                        text: root.tr("Resume", "Wznów")
                        onClicked: root.post("api/resume")
                        contentItem: QQC2.Label { text: parent.text; color: root.c.onAccent; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter }
                        background: Rectangle { radius: 8; color: root.c.accent; implicitHeight: 32 }
                    }
                }
            }

            // ---- talk to Dia (the computer's microphone, as `dia voice toggle`)
            Rectangle {
                id: talkCard
                Layout.fillWidth: true
                implicitHeight: 60
                radius: 12
                color: talkArea.containsMouse ? root.c.hover : root.c.card
                border.color: root.c.borderStrong
                opacity: root.online ? 1 : 0.5
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 12
                    Rectangle {
                        id: orb
                        Layout.preferredWidth: 36; Layout.preferredHeight: 36; radius: 18
                        color: root.voice === "listening" ? root.c.danger : root.voice === "processing" ? root.c.warn
                            : root.speaking ? root.c.accent : root.c.active
                        Kirigami.Icon {
                            anchors.centerIn: parent
                            width: 18; height: 18
                            source: "audio-input-microphone"
                            isMask: true
                            color: root.lit ? root.c.onAccent : root.c.accentInk
                        }
                        SequentialAnimation on opacity {
                            running: root.voice === "listening" || root.voice === "processing"
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.5; duration: 600 }
                            NumberAnimation { to: 1; duration: 600 }
                            onRunningChanged: if (!running) orb.opacity = 1
                        }
                    }
                    ColumnLayout {
                        spacing: 0
                        Layout.fillWidth: true
                        QQC2.Label { Layout.fillWidth: true; text: root.tr("Talk to Dia", "Porozmawiaj z Dią"); color: root.c.text; font.weight: Font.Medium }
                        QQC2.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            text: root.voice === "listening" ? root.tr("Listening… click to stop", "Słucham… kliknij, by skończyć")
                                : root.voice === "processing" ? root.tr("Thinking…", "Myślę…")
                                : root.speaking ? root.tr("Speaking… click to interrupt", "Mówię… kliknij, by przerwać")
                                : root.tr("Middle-click the icon works too", "Działa też środkowy klik w ikonę")
                            color: root.c.muted
                            font.pixelSize: 11
                        }
                    }
                }
                MouseArea {
                    id: talkArea
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: root.online
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.talk()
                }
                Accessible.role: Accessible.Button
                Accessible.name: root.tr("Talk to Dia", "Porozmawiaj z Dią")
            }

            // ---- write to Dia
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 44
                radius: 10
                color: root.c.card
                border.color: ask.activeFocus ? root.c.accent : Qt.rgba(0.71, 0.64, 1, 0.35)
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 6
                    QQC2.TextField {
                        id: ask
                        Layout.fillWidth: true
                        placeholderText: root.tr("Ask or tell Dia…", "Zapytaj lub zleć coś Dii…")
                        placeholderTextColor: root.c.faint
                        color: root.c.text
                        enabled: root.online && !root.asking
                        background: Item {}
                        onAccepted: { root.send(text); text = ""; }
                    }
                    QQC2.ToolButton {
                        icon.name: "go-up"
                        icon.color: root.c.onAccent
                        text: root.tr("Send", "Wyślij")
                        display: QQC2.AbstractButton.IconOnly
                        enabled: root.online && !root.asking && ask.text.trim() !== ""
                        implicitWidth: 32; implicitHeight: 32
                        onClicked: { root.send(ask.text); ask.text = ""; }
                        background: Rectangle { radius: 8; color: root.c.accent; opacity: parent.enabled ? 1 : 0.4 }
                    }
                }
            }

            QQC2.Label {
                Layout.fillWidth: true
                visible: root.asking || root.reply !== ""
                text: root.asking ? root.tr("Thinking…", "Myślę…") : root.reply
                textFormat: Text.MarkdownText
                wrapMode: Text.Wrap
                maximumLineCount: 8
                elide: Text.ElideRight
                color: root.asking ? root.c.muted : root.c.text
            }

            // ---- what waits for you, what runs now
            QQC2.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: 8

                    QQC2.Label {
                        visible: root.waiting.length > 0
                        text: root.tr("WAITING FOR YOU · %1", "CZEKA NA CIEBIE · %1").arg(root.waiting.length)
                        color: root.c.faint
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.4
                    }
                    Repeater {
                        model: root.waiting.slice(0, 4)
                        delegate: waitingCard
                    }

                    QQC2.Label {
                        visible: root.running.length > 0
                        Layout.topMargin: 6
                        text: root.tr("WORKING NOW", "TERAZ PRACUJE")
                        color: root.c.faint
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.4
                    }
                    Repeater {
                        model: root.running.slice(0, 4)
                        delegate: taskRow
                    }

                    QQC2.Label {
                        Layout.fillWidth: true
                        Layout.topMargin: 16
                        visible: root.waiting.length === 0 && root.running.length === 0
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        color: root.c.muted
                        text: root.online ? root.tr("Nothing waits for you. Dia handles the rest.", "Nic nie czeka na Twoją decyzję. Resztą Dia zajmuje się sama.")
                            : root.tr("Start Dia: dia app, or dia service install", "Uruchom Dia: dia app albo dia service install")
                    }
                }
            }

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
                    icon.name: root.quiet ? "audio-volume-muted" : "audio-volume-high"
                    icon.color: root.quiet ? root.c.accentInk : root.c.muted
                    text: root.quiet ? root.tr("Quiet mode: on", "Tryb cichy: włączony")
                        : root.tr("Quiet mode: off", "Tryb cichy: wyłączony")
                    display: QQC2.AbstractButton.IconOnly
                    checkable: true
                    checked: root.quiet
                    enabled: root.online
                    implicitWidth: 36; implicitHeight: 36
                    onClicked: root.post("api/quiet", { on: !root.quiet })
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: text
                    background: Rectangle { radius: 8; color: root.quiet ? root.c.active : parent.hovered ? root.c.hover : "transparent" }
                }
                QQC2.ToolButton {  // two clicks: an emergency stop is not a misclick
                    icon.name: "process-stop"
                    icon.color: root.c.danger
                    text: root.confirmStop ? root.tr("Click again to stop every agent", "Kliknij jeszcze raz, by zatrzymać wszystkich agentów")
                        : root.tr("Emergency stop", "Zatrzymanie awaryjne")
                    display: root.confirmStop ? QQC2.AbstractButton.TextBesideIcon : QQC2.AbstractButton.IconOnly
                    visible: !root.halted
                    enabled: root.online
                    implicitHeight: 36
                    onClicked: {
                        if (root.confirmStop) { root.confirmStop = false; root.post("api/stop"); }
                        else { root.confirmStop = true; stopTimeout.restart(); }
                    }
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: text
                    contentItem: RowLayout {
                        spacing: 6
                        Kirigami.Icon { source: "process-stop"; isMask: true; color: root.c.danger; Layout.preferredWidth: 16; Layout.preferredHeight: 16 }
                        QQC2.Label { visible: root.confirmStop; text: parent.parent.text; color: root.c.danger; font.pixelSize: 12 }
                    }
                    background: Rectangle {
                        radius: 8
                        color: root.confirmStop ? Qt.rgba(0.94, 0.53, 0.54, 0.12) : parent.hovered ? root.c.hover : "transparent"
                        border.color: root.confirmStop ? Qt.rgba(0.94, 0.53, 0.54, 0.4) : "transparent"
                    }
                }
            }
        }
    }

    // A decision waiting for you, as a card in the app's Inbox.
    Component {
        id: waitingCard
        Rectangle {
            id: card
            required property var modelData
            readonly property bool plan: modelData.status === "planned"
            Layout.fillWidth: true
            implicitHeight: cardColumn.implicitHeight + 24
            radius: 12
            color: root.c.card
            border.color: root.c.border
            ColumnLayout {
                id: cardColumn
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8
                RowLayout {
                    spacing: 6
                    Rectangle { Layout.preferredWidth: 6; Layout.preferredHeight: 6; radius: 3; color: card.plan ? root.c.info : root.c.ok }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: card.modelData.project + "  ·  " + card.modelData.agent
                        color: root.c.muted
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                    QQC2.Label {
                        visible: !!card.modelData.diffstat
                        text: card.modelData.diffstat ? "<font color='" + root.c.ok + "'>+" + card.modelData.diffstat.added
                            + "</font> <font color='" + root.c.danger + "'>−" + card.modelData.diffstat.removed + "</font>" : ""
                        textFormat: Text.StyledText
                        font.family: "monospace"
                        font.pixelSize: 11
                    }
                    QQC2.Label {
                        text: card.plan ? root.tr("Plan to approve", "Plan do akceptacji") : root.tr("Ready to merge", "Gotowe do scalenia")
                        color: card.plan ? root.c.info : root.c.ok
                        font.pixelSize: 11
                    }
                }
                QQC2.Label {
                    Layout.fillWidth: true
                    text: card.modelData.prompt.split("\n")[0]
                    color: root.c.text
                    font.weight: Font.Medium
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                RowLayout {
                    spacing: 8
                    QQC2.Button {
                        text: card.plan ? root.tr("Run plan", "Uruchom plan") : root.tr("Review changes", "Sprawdź zmiany")
                        onClicked: card.plan ? root.post("api/tasks/" + card.modelData.id + "/run-plan")
                            : root.openApp("tasks", card.modelData.id)
                        contentItem: QQC2.Label { text: parent.text; color: root.c.onAccent; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { radius: 8; color: root.c.accent; implicitHeight: 32; implicitWidth: 110 }
                    }
                    QQC2.Button {
                        visible: card.plan
                        text: root.tr("Open", "Otwórz")
                        onClicked: root.openApp("tasks", card.modelData.id)
                        contentItem: QQC2.Label { text: parent.text; color: root.c.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { radius: 8; color: parent.hovered ? root.c.hover : "transparent"; border.color: root.c.borderStrong; implicitHeight: 32; implicitWidth: 80 }
                    }
                }
            }
        }
    }

    // A task that runs now: a click opens it in the app.
    Component {
        id: taskRow
        MouseArea {
            id: row
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: rowColumn.implicitHeight + 12
            cursorShape: Qt.PointingHandCursor
            hoverEnabled: true
            onClicked: root.openApp("tasks", modelData.id)
            Rectangle { anchors.fill: parent; radius: 8; color: row.containsMouse ? root.c.hover : "transparent" }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                spacing: 10
                Rectangle { Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4; color: root.statusColor[row.modelData.status] || root.c.faint }
                ColumnLayout {
                    id: rowColumn
                    Layout.fillWidth: true
                    spacing: 0
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: row.modelData.prompt.split("\n")[0]
                        color: root.c.text
                        elide: Text.ElideRight
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: root.taskStatus(row.modelData) + "  ·  " + row.modelData.project + "  ·  " + row.modelData.agent
                        color: root.c.muted
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
}
