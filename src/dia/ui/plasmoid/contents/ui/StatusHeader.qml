// The popup's top: Dia and the connection, the services, the emergency stop banner.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts

ColumnLayout {
    id: part
    required property var panel
    Layout.fillWidth: true
    spacing: 12

        RowLayout {
            spacing: 8
            Image {
                source: part.panel.lit ? part.panel.litIcon : "../images/dia-idle.svg"
                sourceSize: Qt.size(48, 48)
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
            }
            QQC2.Label { text: "dia"; color: part.panel.c.text; font.pixelSize: 20; font.weight: Font.ExtraBold }
            QQC2.Label { text: part.panel.version; color: part.panel.c.faint; font.family: "monospace"; font.pixelSize: 11 }
            Item { Layout.fillWidth: true }
            Rectangle {
                radius: 5
                color: part.panel.online ? Qt.rgba(0.48, 0.85, 0.65, 0.12) : part.panel.c.card
                implicitWidth: connLabel.implicitWidth + 24
                implicitHeight: 24
                Rectangle {
                    width: 6; height: 6; radius: 3
                    anchors.left: parent.left; anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    color: part.panel.online ? part.panel.c.ok : part.panel.c.faint
                }
                QQC2.Label {
                    id: connLabel
                    anchors.left: parent.left; anchors.leftMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    text: part.panel.online ? (part.panel.activeCount > 0 ? part.panel.tr("%1 running", "w toku: %1").arg(part.panel.activeCount)
                        : part.panel.tr("Connected", "Połączono")) : part.panel.tr("Not running", "Nie działa")
                    color: part.panel.online ? part.panel.c.ok : part.panel.c.muted
                    font.pixelSize: 11
                }
            }
            QQC2.ToolButton {
                icon.name: "window-new"
                icon.color: part.panel.c.muted
                text: part.panel.tr("Open Dia", "Otwórz Dia")
                display: QQC2.AbstractButton.IconOnly
                onClicked: part.panel.openApp("", "")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.text: text
                background: Rectangle { radius: 8; color: parent.hovered ? part.panel.c.hover : "transparent" }
            }
        }

        // ---- services: Dia and Ollama
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: services.implicitHeight + 16
            radius: 10
            color: part.panel.c.card
            border.color: part.panel.c.border
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
                        readonly property string unit: (part.panel.serviceState[modelData] || {}).active || ""
                        spacing: 6
                        Rectangle {
                            Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4
                            color: unit === "active" ? part.panel.c.ok : unit === "failed" ? part.panel.c.danger
                                : unit === "activating" || unit === "deactivating" ? part.panel.c.warn : part.panel.c.faint
                        }
                        QQC2.Label { text: modelData === "dia" ? "Dia" : "Ollama"; color: part.panel.c.text }
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: part.panel.serviceStatus(modelData)
                            color: part.panel.c.muted
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                        Repeater {
                            model: [
                                { verb: "start", icon: "media-playback-start", label: part.panel.verbLabel("start") },
                                { verb: "stop", icon: "media-playback-stop", label: part.panel.verbLabel("stop") },
                                { verb: "restart", icon: "view-refresh", label: part.panel.verbLabel("restart") }
                            ]
                            delegate: QQC2.ToolButton {
                                required property var modelData
                                icon.name: modelData.icon
                                icon.color: part.panel.c.muted
                                icon.width: 16; icon.height: 16
                                text: modelData.label
                                display: QQC2.AbstractButton.IconOnly
                                enabled: part.panel.canService(parent.modelData, modelData.verb)
                                implicitWidth: 30; implicitHeight: 30
                                onClicked: part.panel.controlService(parent.modelData, modelData.verb)
                                QQC2.ToolTip.visible: hovered
                                QQC2.ToolTip.text: text
                                background: Rectangle { radius: 6; color: parent.hovered ? part.panel.c.hover : "transparent" }
                            }
                        }
                    }
                }
                QQC2.Label {
                    Layout.fillWidth: true
                    visible: part.panel.serviceResult !== ""
                    text: part.panel.serviceResult
                    color: part.panel.serviceFailed ? part.panel.c.danger : part.panel.c.muted
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
            }
        }

        // ---- emergency stop in force
        Rectangle {
            Layout.fillWidth: true
            visible: part.panel.halted
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
                    text: part.panel.tr("Emergency stop: no agent runs.", "Zatrzymanie awaryjne: żaden agent nie działa.")
                    color: part.panel.c.danger
                    wrapMode: Text.Wrap
                }
                QQC2.Button {
                    text: part.panel.tr("Resume", "Wznów")
                    onClicked: part.panel.post("api/resume")
                    contentItem: QQC2.Label { text: parent.text; color: part.panel.c.onAccent; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter }
                    background: Rectangle { radius: 8; color: part.panel.c.accent; implicitHeight: 32 }
                }
            }
        }
}
