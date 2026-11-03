// A task that runs now: a click opens it in the app.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts

MouseArea {
    id: row
    required property var panel
    required property var modelData
    Layout.fillWidth: true
    implicitHeight: rowColumn.implicitHeight + 12
    cursorShape: Qt.PointingHandCursor
    hoverEnabled: true
    onClicked: row.panel.openApp("tasks", modelData.id)
    Rectangle { anchors.fill: parent; radius: 8; color: row.containsMouse ? row.panel.c.hover : "transparent" }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        spacing: 10
        Rectangle { Layout.preferredWidth: 7; Layout.preferredHeight: 7; radius: 4; color: row.panel.statusColor[row.modelData.status] || row.panel.c.faint }
        ColumnLayout {
            id: rowColumn
            Layout.fillWidth: true
            spacing: 0
            QQC2.Label {
                Layout.fillWidth: true
                text: row.modelData.prompt.split("\n")[0]
                color: row.panel.c.text
                elide: Text.ElideRight
            }
            QQC2.Label {
                Layout.fillWidth: true
                text: row.panel.taskStatus(row.modelData)
                    + (row.modelData.status === "running" ? " " + row.panel.elapsed(row.modelData.created_at) : "")
                    + "  ·  " + row.modelData.project + "  ·  " + row.modelData.agent
                color: row.panel.c.muted
                font.pixelSize: 11
                elide: Text.ElideRight
            }
        }
    }
}
