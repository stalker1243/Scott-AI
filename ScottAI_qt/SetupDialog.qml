import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: setupDialog
    objectName: "setupDialog"
    required property var controller
    required property QtObject theme
    readonly property bool checking: controller.checking === true
    function uiText(value) {
        const source = String(value || "")
        return typeof appLanguage !== "undefined" && appLanguage.language ? qsTranslate("Launcher", source) : source
    }
    transientParent: null
    title: checking ? qsTranslate("Launcher", "Запуск ScottAI") : qsTranslate("Launcher", "Подготовка ScottAI")
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint | Qt.MSWindowsFixedSizeDialogHint
    width: checking ? 440 : 500; height: checking ? 220 : 490
    minimumWidth: 440; maximumWidth: 500; minimumHeight: 220; maximumHeight: 490
    color: theme.popup
    visible: controller.visible
    onClosing: function(close) { controller.cancel(); Qt.quit() }
    background: Rectangle {
        color: setupDialog.theme.popup
        Rectangle { width: parent.width; height: 3; color: setupDialog.theme.accent }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 28; spacing: 10
        RowLayout {
            spacing: 14
            Image { source: "qrc:/brand/scott-logo.png"; Layout.preferredWidth: 54; Layout.preferredHeight: 54 }
            ColumnLayout {
                spacing: 5
                Text { text: "SCOTT AI"; color: setupDialog.theme.muted; font.pixelSize: 11; font.letterSpacing: 2 }
                Text { text: setupDialog.checking ? qsTranslate("Launcher", "Запускаем ScottAI") : qsTranslate("Launcher", "Готовим всё к работе"); color: setupDialog.theme.ink; font.family: setupDialog.theme.fontFamily; font.pixelSize: 23; font.weight: Font.DemiBold }
            }
        }
        Text { visible: !setupDialog.checking; text: qsTranslate("Launcher", "Чат и голос будут готовы после загрузки.\nЭто нужно сделать один раз."); color: setupDialog.theme.muted; font.pixelSize: 13; lineHeight: 1.3; Layout.fillWidth: true }
        Rectangle { visible: !setupDialog.checking; Layout.fillWidth: true; height: 1; color: setupDialog.theme.line }
        UiSwitch {
            objectName: "compactSetupOption"; theme: setupDialog.theme
            visible: !setupDialog.checking
            text: qsTranslate("Launcher", "Компактная установка (CPU)")
            checked: setupDialog.controller.compact; enabled: !setupDialog.controller.busy
            onToggled: setupDialog.controller.compact = checked
        }
        Text {
            objectName: "setupStorageInfo"
            visible: !setupDialog.checking
            text: setupDialog.uiText(setupDialog.controller.sizeHint) || qsTranslate("Launcher", "Чат и голос: около 2 ГиБ на CPU или 5–7 ГиБ на GPU.")
            wrapMode: Text.Wrap
            color: setupDialog.theme.muted; font.pixelSize: 12; lineHeight: 1.25; Layout.fillWidth: true
        }
        Item { Layout.fillHeight: true }
        Text { visible: setupDialog.controller.busy && !setupDialog.checking; text: qsTranslate("Launcher", "Прошло: ") + Math.floor((setupDialog.controller.elapsed || 0) / 60) + qsTranslate("Launcher", " мин. ") + ((setupDialog.controller.elapsed || 0) % 60) + qsTranslate("Launcher", " с"); color: setupDialog.theme.muted; font.pixelSize: 11 }
        ScrollView {
            Layout.fillWidth: true; Layout.preferredHeight: setupDialog.checking ? 28 : 60; clip: true
            contentWidth: availableWidth
            TextArea {
                readOnly: true; selectByMouse: true; padding: 0; wrapMode: Text.Wrap
                text: [setupDialog.uiText(setupDialog.controller.error || setupDialog.controller.message),
                       setupDialog.uiText(diagnosticsController.error || diagnosticsController.notice)].filter(function(value) { return value && value.length }).join("\n\n")
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
            visible: !setupDialog.checking
            Layout.fillWidth: true
            UiButton { objectName: "prepareScottButton"; theme: setupDialog.theme; Layout.fillWidth: true; primary: true; text: setupDialog.controller.busy ? qsTranslate("Launcher", "Подготовка…") : setupDialog.controller.error.length ? qsTranslate("Launcher", "Повторить") : qsTranslate("Launcher", "Продолжить"); enabled: !setupDialog.controller.busy; onClicked: setupDialog.controller.prepare() }
            UiButton { objectName: "cancelSetupButton"; theme: setupDialog.theme; text: qsTranslate("Launcher", "Остановить"); visible: setupDialog.controller.busy; onClicked: setupDialog.controller.cancel() }
            UiButton { objectName: "setupLogsButton"; theme: setupDialog.theme; text: diagnosticsController.busy ? qsTranslate("Launcher", "Сбор…") : qsTranslate("Launcher", "Логи"); enabled: !diagnosticsController.busy; onClicked: diagnosticsController.exportArchive() }
        }
    }
}
