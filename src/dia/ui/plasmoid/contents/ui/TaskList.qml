// What waits for your decision and what runs now.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts

    QQC2.ScrollView {
    id: list
    required property var panel
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 8

            QQC2.Label {
                visible: list.panel.waiting.length > 0
                text: list.panel.tr("WAITING FOR YOU · %1", "CZEKA NA CIEBIE · %1").arg(list.panel.waitingCount)
                color: list.panel.c.faint
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.letterSpacing: 1.4
            }
            Repeater {
                model: list.panel.waiting.slice(0, 4)
                delegate: waitingCard
            }

            QQC2.Label {
                visible: list.panel.running.length > 0
                Layout.topMargin: 6
                text: list.panel.tr("WORKING NOW", "TERAZ PRACUJE")
                color: list.panel.c.faint
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.letterSpacing: 1.4
            }
            Repeater {
                model: list.panel.running.slice(0, 4)
                delegate: taskRow
            }

            QQC2.Label {
                Layout.fillWidth: true
                Layout.topMargin: 16
                visible: list.panel.waiting.length === 0 && list.panel.running.length === 0
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: list.panel.c.muted
                text: list.panel.online ? list.panel.tr("Nothing waits for you. Dia handles the rest.", "Nic nie czeka na Twoją decyzję. Resztą Dia zajmuje się sama.")
                    : list.panel.tr("Start Dia: dia app, or dia service install", "Uruchom Dia: dia app albo dia service install")
            }
        }
    
    Component {
        id: waitingCard
        WaitingCard { panel: list.panel }
    }
    Component {
        id: taskRow
        TaskRow { panel: list.panel }
    }
}
