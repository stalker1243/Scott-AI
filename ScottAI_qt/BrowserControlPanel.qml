import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: panel
    objectName: "browserControlPanel"
    required property QtObject theme
    required property QtObject controller
    readonly property var state: controller.browserState || ({})
    readonly property bool running: state.state === "running" || state.state === "cancelling"
    readonly property bool usable: controller.online && controller.browserReady && !running
    width: Math.min(390, parent.width - 32)
    height: Math.min(body.implicitHeight + 28, parent.height - 90)
    x: parent.width - width - 18; y: 70
    padding: 14; modal: false; focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onAboutToShow: controller.refreshBrowser()
    background: Rectangle { color: panel.theme.popup; radius: panel.theme.cardRadius; border.color: panel.theme.line }
    contentItem: ScrollView {
        id: viewport
        clip: true; contentWidth: availableWidth
        ColumnLayout {
            id: body
            width: viewport.availableWidth
            spacing: 10
            RowLayout {
                Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Браузер Scott"); color: panel.theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold }
                UiButton { theme: panel.theme; text: "×"; implicitWidth: 28; implicitHeight: 28; leftPadding: 0; rightPadding: 0; onClicked: panel.close() }
            }
            Text { Layout.fillWidth: true; text: panel.state.installed ? qsTranslate("Launcher", "YouTube: поиск, выбор видео, пауза и продолжение.") : qsTranslate("Launcher", "Подготовьте управление. Scott откроет отдельное окно браузера с собственным профилем."); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: panel.theme.muted; font.pixelSize: 12 }
            RowLayout {
                UiButton {
                    objectName: "browserPrepareButton"; theme: panel.theme
                    text: panel.state.installed ? qsTranslate("Launcher", "Проверить подготовку") : qsTranslate("Launcher", "Подготовить")
                    implicitHeight: 32; font.pixelSize: 12; enabled: panel.usable
                    onClicked: panel.controller.startBrowser("install")
                }
                UiButton { theme: panel.theme; visible: !!panel.state.installed; text: panel.state.enabled ? qsTranslate("Launcher", "Отключить") : qsTranslate("Launcher", "Включить"); implicitHeight: 32; font.pixelSize: 12; enabled: panel.usable; onClicked: panel.controller.setBrowserEnabled(!panel.state.enabled) }
            }
            Text { objectName: "browserStep"; Layout.fillWidth: true; text: !panel.controller.online ? qsTranslate("Launcher", "Нет подключения к Scott") : panel.state.message || qsTranslate("Launcher", "Напишите в чате: «найди на YouTube уроки Python»."); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: panel.state.state === "failed" ? panel.theme.danger : panel.theme.ink; font.pixelSize: 12 }
            ProgressBar { visible: panel.running; Layout.fillWidth: true; from: 0; to: 1; value: panel.state.progress || 0; indeterminate: panel.state.stage === "starting" }
            UiButton { objectName: "browserStopButton"; theme: panel.theme; text: panel.state.state === "cancelling" ? qsTranslate("Launcher", "Останавливаем…") : qsTranslate("Launcher", "Стоп"); visible: panel.running; enabled: panel.controller.online && panel.controller.browserReady && panel.state.state === "running"; implicitHeight: 32; onClicked: panel.controller.cancelBrowser() }
            RowLayout {
                visible: !!panel.state.installed && !!panel.state.enabled
                UiButton { theme: panel.theme; text: qsTranslate("Launcher", "Пауза"); implicitHeight: 30; font.pixelSize: 12; enabled: panel.usable && !!panel.state.browser_open; onClicked: panel.controller.startBrowser("pause") }
                UiButton { theme: panel.theme; text: qsTranslate("Launcher", "Продолжить"); implicitHeight: 30; font.pixelSize: 12; enabled: panel.usable && !!panel.state.browser_open; onClicked: panel.controller.startBrowser("resume") }
                UiButton { theme: panel.theme; text: qsTranslate("Launcher", "Закрыть"); implicitHeight: 30; font.pixelSize: 12; enabled: panel.usable && !!panel.state.browser_open; onClicked: panel.controller.startBrowser("close") }
            }
            Text { visible: !!(panel.state.playback || {}).verified; Layout.fillWidth: true; text: qsTranslate("Launcher", "Проверено: ") + ((panel.state.playback || {}).paused ? qsTranslate("Launcher", "пауза · ") : qsTranslate("Launcher", "воспроизведение · ")) + ((panel.state.playback || {}).title || "YouTube"); textFormat: Text.PlainText; wrapMode: Text.Wrap; color: panel.theme.success; font.pixelSize: 12 }
            Repeater {
                model: panel.state.candidates || []
                delegate: UiButton {
                    required property var modelData
                    required property int index
                    objectName: "browserResult" + index
                    theme: panel.theme; Layout.fillWidth: true; implicitHeight: 44
                    enabled: panel.usable && !!panel.state.enabled
                    contentItem: Text {
                        text: (index + 1) + ". " + modelData.title; textFormat: Text.PlainText
                        wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                        color: panel.theme.ink; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: panel.controller.startBrowser("select", "", index)
                }
            }
        }
    }
}
