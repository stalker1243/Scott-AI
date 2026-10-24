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
    title: checking || controller.prepared ? qsTranslate("Launcher", "Запуск ScottAI") : qsTranslate("Launcher", "Подготовка ScottAI")
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint | Qt.MSWindowsFixedSizeDialogHint
    width: checking ? 440 : 520; height: checking ? 220 : 550
    minimumWidth: 440; maximumWidth: 520; minimumHeight: 220; maximumHeight: 550
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
            ScottMark { color: theme.ink; Layout.preferredWidth: 54; Layout.preferredHeight: 54 }
            ColumnLayout {
                spacing: 5
                Text { text: "SCOTT AI"; color: setupDialog.theme.muted; font.pixelSize: 11; font.letterSpacing: 2 }
                Text { text: setupDialog.checking || controller.prepared ? qsTranslate("Launcher", "Запускаем ScottAI") : qsTranslate("Launcher", "Готовим всё к работе"); color: setupDialog.theme.ink; font.family: setupDialog.theme.fontFamily; font.pixelSize: 23; font.weight: Font.DemiBold }
            }
        }
        Rectangle { visible: !setupDialog.checking; Layout.fillWidth: true; height: 1; color: setupDialog.theme.line }
        UiComboBox {
            id: modePicker
            objectName: "runtimeSetupOption"; theme: setupDialog.theme
            Layout.fillWidth: true
            visible: !setupDialog.checking && !controller.prepared
            model: [qsTranslate("Launcher", "Автоматически"), qsTranslate("Launcher", "Обычный CPU")]
            translateDisplay: false
            currentIndex: ["auto", "cpu"].indexOf(setupDialog.controller.runtimeMode)
            displayText: currentIndex < 0 ? qsTranslate("Launcher", "Сохранённый режим") : currentText
            enabled: !setupDialog.controller.busy
            onActivated: setupDialog.controller.runtimeMode = ["auto", "cpu"][currentIndex]
        }
        Text {
            objectName: "setupModeDescription"
            visible: modePicker.visible
            text: setupDialog.controller.runtimeMode === "cpu"
                  ? qsTranslate("Launcher", "Полный набор движков распознавания на CPU. Scott Voice можно подготовить отдельно на главном экране.")
                  : qsTranslate("Launcher", "Ускорение подбирается для вашего компьютера. Сохраняются прежние настройки распознавания. Scott Voice готовится отдельно.")
            color: setupDialog.theme.ink; font.pixelSize: 12; lineHeight: 1.2
            wrapMode: Text.Wrap; Layout.fillWidth: true
        }
        Text {
            objectName: "setupStorageInfo"
            visible: !setupDialog.checking && !controller.prepared
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
            UiButton { objectName: "prepareScottButton"; theme: setupDialog.theme; Layout.fillWidth: true; primary: true; text: setupDialog.controller.busy ? qsTranslate("Launcher", "Подготовка…") : controller.prepared ? qsTranslate("Launcher", "Повторить запуск") : setupDialog.controller.error.length ? qsTranslate("Launcher", "Повторить") : qsTranslate("Launcher", "Продолжить"); enabled: !setupDialog.controller.busy; onClicked: setupDialog.controller.prepare() }
            UiButton { objectName: "cancelSetupButton"; theme: setupDialog.theme; text: qsTranslate("Launcher", "Остановить"); visible: setupDialog.controller.busy; onClicked: setupDialog.controller.cancel() }
            UiButton { objectName: "setupLogsButton"; theme: setupDialog.theme; text: diagnosticsController.busy ? qsTranslate("Launcher", "Сбор…") : qsTranslate("Launcher", "Логи"); enabled: !diagnosticsController.busy; onClicked: diagnosticsController.exportArchive() }
        }
    }
}
