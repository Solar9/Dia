// A task that waits for your decision: a plan to approve or changes to review.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts

Rectangle {
    id: card
    required property var panel
    required property var modelData
    readonly property bool plan: modelData.status === "planned"
    Layout.fillWidth: true
    implicitHeight: cardColumn.implicitHeight + 24
    radius: 12
    color: card.panel.c.card
    border.color: card.panel.c.border
    ColumnLayout {
        id: cardColumn
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8
        RowLayout {
            spacing: 6
            Rectangle { Layout.preferredWidth: 6; Layout.preferredHeight: 6; radius: 3; color: card.plan ? card.panel.c.info : card.panel.c.ok }
            QQC2.Label {
                Layout.fillWidth: true
                text: card.modelData.project + "  ·  " + card.modelData.agent
                color: card.panel.c.muted
                font.pixelSize: 11
                elide: Text.ElideRight
            }
            QQC2.Label {
                visible: !!card.modelData.diffstat
                text: card.modelData.diffstat ? "<font color='" + card.panel.c.ok + "'>+" + card.modelData.diffstat.added
                    + "</font> <font color='" + card.panel.c.danger + "'>−" + card.modelData.diffstat.removed + "</font>" : ""
                textFormat: Text.StyledText
                font.family: "monospace"
                font.pixelSize: 11
            }
            QQC2.Label {
                text: card.plan ? card.panel.tr("Plan to approve", "Plan do akceptacji") : card.panel.tr("Ready to merge", "Gotowe do scalenia")
                color: card.plan ? card.panel.c.info : card.panel.c.ok
                font.pixelSize: 11
            }
        }
        QQC2.Label {
            Layout.fillWidth: true
            text: card.modelData.prompt.split("\n")[0]
            color: card.panel.c.text
            font.weight: Font.Medium
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
        RowLayout {
            spacing: 8
            QQC2.Button {
                text: card.plan ? card.panel.tr("Run plan", "Uruchom plan") : card.panel.tr("Review changes", "Sprawdź zmiany")
                onClicked: card.plan ? card.panel.post("api/tasks/" + card.modelData.id + "/run-plan")
                    : card.panel.openApp("tasks", card.modelData.id)
                contentItem: QQC2.Label { text: parent.text; color: card.panel.c.onAccent; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 8; color: card.panel.c.accent; implicitHeight: 32; implicitWidth: 110 }
            }
            QQC2.Button {
                visible: card.plan
                text: card.panel.tr("Open", "Otwórz")
                onClicked: card.panel.openApp("tasks", card.modelData.id)
                contentItem: QQC2.Label { text: parent.text; color: card.panel.c.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 8; color: parent.hovered ? card.panel.c.hover : "transparent"; border.color: card.panel.c.borderStrong; implicitHeight: 32; implicitWidth: 80 }
            }
        }
    }
}
