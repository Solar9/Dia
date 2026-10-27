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
import org.kde.plasma.extras as PlasmaExtras
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

    readonly property var statusColor: ({
        "done": Kirigami.Theme.positiveTextColor, "merged": Kirigami.Theme.positiveTextColor,
        "failed": Kirigami.Theme.negativeTextColor, "running": Kirigami.Theme.neutralTextColor,
        "queued": Kirigami.Theme.neutralTextColor, "planned": Kirigami.Theme.linkColor,
        "published": Kirigami.Theme.linkColor
    })

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

    onExpandedChanged: if (expanded) refresh()

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
            source: root.lit ? "../images/dia.svg" : "../images/dia-idle.svg"
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
            color: Kirigami.Theme.highlightColor
            PlasmaComponents.Label {
                id: badge
                anchors.centerIn: parent
                text: root.waiting.length
                color: Kirigami.Theme.highlightedTextColor
                font.pixelSize: parent.height * 0.75
                font.bold: true
            }
        }
    }

    fullRepresentation: ColumnLayout {
        QQC2.Dialog {
            id: serviceConfirm
            title: root.tr("Confirm service action", "Potwierdź zmianę usług")
            modal: true
            standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
            onAccepted: root.executeService()
            contentItem: PlasmaComponents.Label {
                text: root.pendingComponent + ": " + root.pendingVerb + "\n"
                    + root.tr("Active tasks may be interrupted. Continue?", "Aktywne zadania mogą zostać przerwane. Kontynuować?")
                wrapMode: Text.Wrap
            }
        }
        Layout.preferredWidth: Kirigami.Units.gridUnit * 24
        Layout.preferredHeight: Kirigami.Units.gridUnit * 30
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Image {
                source: root.lit ? "../images/dia.svg" : "../images/dia-idle.svg"
                sourceSize: Qt.size(Kirigami.Units.iconSizes.medium * 2, Kirigami.Units.iconSizes.medium * 2)
                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
            }
            Kirigami.Heading { level: 3; text: "Dia" }
            PlasmaComponents.Label { text: root.version; opacity: 0.6; Layout.fillWidth: true }
            PlasmaComponents.Label {
                text: root.online ? root.tr("Connected", "Połączono") : root.tr("Not running", "Nie działa")
                color: root.online ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
            }
        }

        Repeater {
            model: ["dia", "ollama"]
            delegate: RowLayout {
                required property string modelData
                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: (modelData === "dia" ? "Dia" : "Ollama") + ": " + root.serviceStatus(modelData)
                }
                PlasmaComponents.Button {
                    text: root.tr("Start", "Uruchom")
                    enabled: !root.serviceBusy
                    onClicked: root.controlService(modelData, "start")
                }
                PlasmaComponents.ToolButton {
                    icon.name: "media-playback-stop"
                    text: root.tr("Stop", "Zatrzymaj")
                    enabled: !root.serviceBusy
                    onClicked: root.controlService(modelData, "stop")
                }
                PlasmaComponents.ToolButton {
                    icon.name: "view-refresh"
                    text: root.tr("Restart", "Restart")
                    enabled: !root.serviceBusy
                    onClicked: root.controlService(modelData, "restart")
                }
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: root.halted
            type: Kirigami.MessageType.Error
            text: root.tr("Emergency stop: no agent runs.", "Zatrzymanie awaryjne: żaden agent nie działa.")
            actions: [
                Kirigami.Action {
                    text: root.tr("Resume", "Wznów")
                    onTriggered: root.post("api/resume")
                }
            ]
        }

        PlasmaComponents.Button {
            Layout.fillWidth: true
            icon.name: root.voice === "listening" ? "audio-input-microphone-high" : "audio-input-microphone"
            text: root.voice === "listening" ? root.tr("Listening… click to stop", "Słucham… kliknij, by skończyć")
                : root.voice === "processing" ? root.tr("Thinking…", "Myślę…")
                : root.speaking ? root.tr("Speaking… click to interrupt", "Mówię… kliknij, by przerwać")
                : root.tr("Talk to Dia", "Mów do Dia")
            enabled: root.online
            onClicked: root.talk()
        }

        RowLayout {
            PlasmaComponents.TextField {
                id: ask
                Layout.fillWidth: true
                placeholderText: root.tr("Write to Dia…", "Napisz do Dia…")
                enabled: root.online && !root.asking
                onAccepted: { root.send(text); text = ""; }
            }
            PlasmaComponents.ToolButton {
                icon.name: "document-send"
                enabled: root.online && !root.asking && ask.text.trim() !== ""
                onClicked: { root.send(ask.text); ask.text = ""; }
            }
        }

        PlasmaComponents.Label {
            Layout.fillWidth: true
            visible: root.asking || root.reply !== ""
            text: root.asking ? root.tr("Thinking…", "Myślę…") : root.reply
            textFormat: Text.MarkdownText
            wrapMode: Text.Wrap
            maximumLineCount: 10
            elide: Text.ElideRight
            opacity: root.asking ? 0.6 : 1
        }

        PlasmaExtras.Heading {
            visible: root.waiting.length > 0
            level: 5
            text: root.tr("Waiting for you", "Czeka na Ciebie") + " (" + root.waiting.length + ")"
            color: Kirigami.Theme.highlightColor
        }

        Repeater {
            model: root.waiting.slice(0, 4)
            delegate: taskRow
        }

        PlasmaExtras.Heading { level: 5; text: root.tr("Recent tasks", "Ostatnie zadania"); opacity: 0.7 }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.tasks.slice(0, 10)
            delegate: taskRow
            PlasmaExtras.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.gridUnit * 2
                visible: parent.count === 0
                text: root.online ? root.tr("No tasks yet", "Na razie brak zadań")
                    : root.tr("Start Dia: dia app, or dia service install", "Uruchom Dia: dia app albo dia service install")
            }
        }

        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Button {
                Layout.fillWidth: true
                icon.name: "io.github.solar9.dia"
                text: root.tr("Open Dia", "Otwórz Dia")
                onClicked: root.openApp("", "")
            }
            PlasmaComponents.ToolButton {
                icon.name: "dialog-messages"
                text: root.tr("Chat", "Czat")
                display: QQC2.AbstractButton.IconOnly
                onClicked: root.openApp("chat", "")
                PlasmaComponents.ToolTip { text: parent.text }
            }
            PlasmaComponents.ToolButton {
                icon.name: "view-statistics"
                text: root.tr("Status", "Status")
                display: QQC2.AbstractButton.IconOnly
                onClicked: root.openApp("status", "")
                PlasmaComponents.ToolTip { text: parent.text }
            }
            PlasmaComponents.ToolButton {
                icon.name: "configure"
                text: root.tr("Settings", "Ustawienia")
                display: QQC2.AbstractButton.IconOnly
                onClicked: root.openApp("settings", "")
                PlasmaComponents.ToolTip { text: parent.text }
            }
            PlasmaComponents.ToolButton {
                icon.name: root.quiet ? "audio-volume-muted" : "audio-volume-high"
                text: root.quiet ? root.tr("Quiet mode: on", "Tryb cichy: włączony")
                    : root.tr("Quiet mode: off", "Tryb cichy: wyłączony")
                display: QQC2.AbstractButton.IconOnly
                checkable: true
                checked: root.quiet
                enabled: root.online
                onClicked: root.post("api/quiet", { on: !root.quiet })
                PlasmaComponents.ToolTip { text: parent.text }
            }
            PlasmaComponents.ToolButton {  // two clicks: an emergency stop is not a misclick
                icon.name: "process-stop"
                text: root.confirmStop ? root.tr("Click again to stop every agent", "Kliknij jeszcze raz, by zatrzymać wszystkich agentów")
                    : root.tr("Emergency stop", "Zatrzymanie awaryjne")
                display: root.confirmStop ? QQC2.AbstractButton.TextBesideIcon : QQC2.AbstractButton.IconOnly
                visible: !root.halted
                enabled: root.online
                onClicked: {
                    if (root.confirmStop) { root.confirmStop = false; root.post("api/stop"); }
                    else { root.confirmStop = true; stopTimeout.restart(); }
                }
                PlasmaComponents.ToolTip { text: parent.text }
            }
        }
    }

    Component {
        id: taskRow
        MouseArea {
            width: ListView.view ? ListView.view.width : parent.width
            Layout.fillWidth: true
            implicitHeight: rowColumn.implicitHeight + Kirigami.Units.smallSpacing
            cursorShape: Qt.PointingHandCursor
            onClicked: root.openApp("tasks", modelData.id)
            ColumnLayout {
                id: rowColumn
                width: parent.width
                spacing: 0
                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: modelData.prompt.split("\n")[0]
                    elide: Text.ElideRight
                }
                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: "● " + root.taskStatus(modelData) + "  ·  " + modelData.project + "  ·  " + modelData.agent
                    color: root.statusColor[modelData.status] || Kirigami.Theme.disabledTextColor
                    font: Kirigami.Theme.smallFont
                    elide: Text.ElideRight
                }
            }
        }
    }
}
