import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: page
    required property var controller
    required property QtObject theme
    spacing: 12
    RowLayout {
        Layout.fillWidth: true
        Text { text: qsTranslate("Launcher", "Логи"); color: page.theme.ink; font.pixelSize: 24; font.weight: Font.DemiBold; Layout.fillWidth: true }
        UiButton { objectName: "refreshLogsButton"; theme: page.theme; text: qsTranslate("Launcher", "Обновить"); enabled: !page.controller.busy; onClicked: page.controller.refresh(logChoice.currentValue || "backend-process.log") }
        UiButton { objectName: "exportLogsButton"; theme: page.theme; text: qsTranslate("Launcher", "Собрать архив"); primary: true; enabled: !page.controller.busy; onClicked: page.controller.exportArchive() }
    }
    Text { text: qsTranslate("Launcher", "Журналы запуска и установки. Работают даже без подключения к backend."); color: page.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        UiComboBox {
            theme: page.theme
            id: logChoice; objectName: "logChoice"; Layout.fillWidth: true
            model: page.controller.logs; textRole: "name"; valueRole: "name"
            currentIndex: { for (let i = 0; i < model.length; ++i) if (model[i].name === page.controller.selectedName) return i; return 0 }
            enabled: !page.controller.busy
            onActivated: page.controller.refresh(currentValue)
        }
        UiButton { theme: page.theme; text: qsTranslate("Launcher", "Папка"); onClicked: page.controller.openFolder() }
        BusyIndicator { running: page.controller.busy; implicitWidth: 28; implicitHeight: 28; visible: running }
    }
    Rectangle {
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 120
        color: page.theme.surface; radius: page.theme.controlRadius; border.color: page.theme.line
        ScrollView {
            anchors.fill: parent; anchors.margins: 12; clip: true
            contentWidth: availableWidth
            TextArea {
                objectName: "logText"; text: page.controller.text || qsTranslate("Launcher", "Нажмите «Обновить», чтобы прочитать журнал.")
                readOnly: true; selectByMouse: true; wrapMode: Text.Wrap; padding: 0
                color: page.theme.ink; font.family: "Consolas"; font.pixelSize: 12; background: null
            }
        }
    }
    Text {
        text: page.controller.error || page.controller.notice
        visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true
        color: page.controller.error ? page.theme.danger : page.theme.muted; font.pixelSize: 12
    }
    Text { text: qsTranslate("Launcher", "В архив входят технические логи и сведения о системе. API Token скрываются; история чатов и вложения не добавляются."); color: page.theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
}
