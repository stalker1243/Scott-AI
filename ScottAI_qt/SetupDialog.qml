import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: setupDialog
    objectName: "setupDialog"
    required property var controller
    required property QtObject theme
    transientParent: null
    title: "Подготовка ScottAI"
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint
    width: 500; height: 490
    minimumWidth: 500; maximumWidth: 500; minimumHeight: 490; maximumHeight: 490
    color: theme.popup
    visible: controller.visible
    onClosing: function(close) { controller.cancel(); Qt.quit() }
    background: Rectangle {
        color: setupDialog.theme.popup
        Rectangle { width: parent.width; height: 3; color: setupDialog.theme.accent }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 28; spacing: 14
        RowLayout {
            spacing: 14
            Image { source: "qrc:/brand/scott-logo.png"; Layout.preferredWidth: 54; Layout.preferredHeight: 54 }
            ColumnLayout {
                spacing: 5
                Text { text: "SCOTT AI"; color: setupDialog.theme.muted; font.pixelSize: 11; font.letterSpacing: 2 }
                Text { text: "Готовим всё к работе"; color: setupDialog.theme.ink; font.family: setupDialog.theme.fontFamily; font.pixelSize: 23; font.weight: Font.DemiBold }
            }
        }
        Text { text: "Чат и голос будут готовы после загрузки.\nЭто нужно сделать один раз."; color: setupDialog.theme.muted; font.pixelSize: 13; lineHeight: 1.3; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: setupDialog.theme.line }
        UiSwitch {
            objectName: "compactSetupOption"; theme: setupDialog.theme
            text: "Компактная установка (CPU)"
            checked: setupDialog.controller.compact; enabled: !setupDialog.controller.busy
            onToggled: setupDialog.controller.compact = checked
        }
        Text {
            text: setupDialog.controller.compact ? "Меньше места и загрузок. Чат и голос сохраняются;\nречь обрабатывает процессор." : "Ускорение на видеокарте определяется автоматически.\nGPU-библиотеки могут занимать несколько гигабайт."
            color: setupDialog.theme.muted; font.pixelSize: 12; lineHeight: 1.25; Layout.fillWidth: true
        }
        Item { Layout.fillHeight: true }
        ScrollView {
            Layout.fillWidth: true; Layout.preferredHeight: 72; clip: true
            contentWidth: availableWidth
            TextArea {
                readOnly: true; selectByMouse: true; padding: 0; wrapMode: Text.Wrap
                text: setupDialog.controller.error || setupDialog.controller.message
                color: setupDialog.controller.error.length ? setupDialog.theme.danger : setupDialog.theme.ink
                font.pixelSize: 12; background: null
            }
        }
        ProgressBar {
            id: progressBar; Layout.fillWidth: true; implicitHeight: 6
            value: setupDialog.controller.progress
            indeterminate: setupDialog.controller.busy && value === 0
            background: Rectangle { color: setupDialog.theme.line; radius: 3 }
            contentItem: Item {
                clip: true
                Rectangle {
                    width: progressBar.indeterminate ? parent.width * 0.3 : parent.width * progressBar.visualPosition
                    height: parent.height; radius: 3; color: setupDialog.theme.accent
                    x: progressBar.indeterminate ? -width + (parent.width + width) * sweep : 0
                    property real sweep: 0
                    NumberAnimation on sweep { from: 0; to: 1; duration: 1400; loops: Animation.Infinite; running: progressBar.indeterminate }
                    Behavior on width { NumberAnimation { duration: 160 } }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            UiButton { objectName: "prepareScottButton"; theme: setupDialog.theme; Layout.fillWidth: true; primary: true; text: setupDialog.controller.busy ? "Подготовка…" : setupDialog.controller.error.length ? "Повторить" : "Продолжить"; enabled: !setupDialog.controller.busy; onClicked: setupDialog.controller.prepare() }
            UiButton { objectName: "cancelSetupButton"; theme: setupDialog.theme; text: "Остановить"; visible: setupDialog.controller.busy; onClicked: setupDialog.controller.cancel() }
        }
    }
}
