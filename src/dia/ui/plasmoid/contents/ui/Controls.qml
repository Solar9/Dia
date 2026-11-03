// Talk to Dia, write to Dia, and her latest answer.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: part
    required property var panel
    Layout.fillWidth: true
    spacing: 12

        Rectangle {
            id: talkCard
            Layout.fillWidth: true
            implicitHeight: 60
            radius: 12
            color: talkArea.containsMouse ? part.panel.c.hover : part.panel.c.card
            border.color: part.panel.c.borderStrong
            opacity: part.panel.online ? 1 : 0.5
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12
                Rectangle {
                    id: orb
                    Layout.preferredWidth: 36; Layout.preferredHeight: 36; radius: 18
                    color: part.panel.voice === "listening" ? part.panel.c.danger : part.panel.voice === "processing" ? part.panel.c.warn
                        : part.panel.speaking ? part.panel.c.accent : part.panel.c.active
                    Kirigami.Icon {
                        anchors.centerIn: parent
                        width: 18; height: 18
                        source: "audio-input-microphone"
                        isMask: true
                        color: part.panel.lit ? part.panel.c.onAccent : part.panel.c.accentInk
                    }
                    SequentialAnimation on opacity {
                        running: part.panel.voice === "listening" || part.panel.voice === "processing"
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.5; duration: 600 }
                        NumberAnimation { to: 1; duration: 600 }
                        onRunningChanged: if (!running) orb.opacity = 1
                    }
                }
                ColumnLayout {
                    spacing: 0
                    Layout.fillWidth: true
                    QQC2.Label { Layout.fillWidth: true; text: part.panel.tr("Talk to Dia", "Porozmawiaj z Dią"); color: part.panel.c.text; font.weight: Font.Medium }
                    QQC2.Label {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: part.panel.voice === "listening" ? part.panel.tr("Listening… click to stop", "Słucham… kliknij, by skończyć")
                            : part.panel.voice === "processing" ? part.panel.tr("Thinking…", "Myślę…")
                            : part.panel.speaking ? part.panel.tr("Speaking… click to interrupt", "Mówię… kliknij, by przerwać")
                            : part.panel.tr("Middle-click the icon works too", "Działa też środkowy klik w ikonę")
                        color: part.panel.c.muted
                        font.pixelSize: 11
                    }
                }
            }
            MouseArea {
                id: talkArea
                anchors.fill: parent
                hoverEnabled: true
                enabled: part.panel.online
                cursorShape: Qt.PointingHandCursor
                onClicked: part.panel.talk()
            }
            Accessible.role: Accessible.Button
            Accessible.name: part.panel.tr("Talk to Dia", "Porozmawiaj z Dią")
        }

        // ---- write to Dia
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 44
            radius: 10
            color: part.panel.c.card
            border.color: ask.activeFocus ? part.panel.c.accent : Qt.rgba(0.71, 0.64, 1, 0.35)
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 6
                QQC2.TextField {
                    id: ask
                    Layout.fillWidth: true
                    placeholderText: part.panel.tr("Ask or tell Dia…", "Zapytaj lub zleć coś Dii…")
                    placeholderTextColor: part.panel.c.faint
                    color: part.panel.c.text
                    enabled: part.panel.online && !part.panel.asking
                    background: Item {}
                    onAccepted: { if (part.panel.send(text)) text = ""; }
                }
                QQC2.ToolButton {
                    icon.name: "go-up"
                    icon.color: part.panel.c.onAccent
                    text: part.panel.tr("Send", "Wyślij")
                    display: QQC2.AbstractButton.IconOnly
                    enabled: part.panel.online && !part.panel.asking && ask.text.trim() !== ""
                    implicitWidth: 32; implicitHeight: 32
                    onClicked: { if (part.panel.send(ask.text)) ask.text = ""; }
                    background: Rectangle { radius: 8; color: part.panel.c.accent; opacity: parent.enabled ? 1 : 0.4 }
                }
            }
        }

        // A long answer scrolls inside its own box instead of being cut off or growing the popup.
        QQC2.ScrollView {
            id: answerBox
            objectName: "answerBox"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(answer.implicitHeight, 160)
            visible: part.panel.asking || part.panel.reply !== ""
            clip: true
            QQC2.Label {
                id: answer
                objectName: "answer"
                width: answerBox.availableWidth
                text: part.panel.asking ? part.panel.tr("Thinking…", "Myślę…") : part.panel.reply
                textFormat: Text.MarkdownText
                wrapMode: Text.Wrap
                color: part.panel.asking ? part.panel.c.muted : part.panel.c.text
            }
        }
}
