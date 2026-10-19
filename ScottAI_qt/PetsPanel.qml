import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "PetCatalog.js" as Pets

ColumnLayout {
    id: panel
    required property QtObject theme
    required property var controller
    readonly property var selected: Pets.find(controller.kind)
    spacing: 12
    RowLayout {
        Layout.fillWidth: true; spacing: 6
        Repeater {
            model: Pets.pets
            delegate: Button {
                id: card
                required property var modelData
                required property int index
                objectName: "petChoice" + index
                Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 120; padding: 5
                Accessible.name: qsTranslate("Launcher", modelData.name)
                onClicked: panel.controller.selectPet(modelData.id)
                background: Rectangle { radius: 12; color: panel.controller.kind === card.modelData.id ? Qt.alpha(panel.theme.accent, 0.08) : "transparent"; border.color: panel.controller.kind === card.modelData.id || card.visualFocus ? panel.theme.accent : panel.theme.line }
                contentItem: ColumnLayout {
                    spacing: 4
                    PetCharacter { Layout.fillWidth: true; Layout.fillHeight: true; interactive: false; kind: card.modelData.id; variant: panel.controller.kind === kind ? panel.controller.variant : card.modelData.colors[0]; motion: panel.theme.motion; demo: true }
                    Text { text: qsTranslate("Launcher", card.modelData.name); Layout.alignment: Qt.AlignHCenter; color: panel.theme.ink; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 12
        PetCharacter { id: demoPet; objectName: "petLargePreview"; Layout.preferredWidth: 154; Layout.preferredHeight: 154; kind: panel.controller.kind; variant: panel.controller.variant; motion: panel.theme.motion && panel.controller.motion; demo: true }
        ColumnLayout {
            Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 6
            Text { text: qsTranslate("Launcher", panel.selected.detail); Layout.fillWidth: true; color: panel.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
            RowLayout {
                spacing: 4
                Repeater {
                    model: panel.selected.colors
                    delegate: Button {
                        id: swatch
                        required property string modelData
                        objectName: "petColor_" + modelData
                        implicitWidth: 34; implicitHeight: 34; hoverEnabled: true
                        Accessible.name: qsTranslate("Launcher", Pets.colorNames[modelData])
                        ToolTip.visible: hovered; ToolTip.text: Accessible.name
                        onClicked: panel.controller.selectVariant(modelData)
                        background: Rectangle { anchors.fill: parent; anchors.margins: 3; radius: 14; color: Pets.color(swatch.modelData); border.width: panel.controller.variant === swatch.modelData ? 2 : 0; border.color: panel.theme.ink }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: qsTranslate("Launcher", "Размер"); color: panel.theme.ink; font.pixelSize: 12 }
                Text { Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; text: panel.controller.sizePercent + "%"; color: panel.theme.muted; font.pixelSize: 12 }
            }
            UiSlider { objectName: "petSizeSlider"; theme: panel.theme; Layout.fillWidth: true; from: 50; to: 200; stepSize: 5; value: panel.controller.sizePercent; Accessible.name: qsTranslate("Launcher", "Размер питомца"); onMoved: panel.controller.setSizePercent(Math.round(value)) }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "На рабочем столе"); color: panel.theme.ink; font.pixelSize: 13 }
        UiSwitch { objectName: "desktopPetToggle"; theme: panel.theme; checked: panel.controller.enabled; enabled: !panel.controller.busy; onToggled: panel.controller.setEnabled(checked) }
    }
    RowLayout {
        Layout.fillWidth: true
        ChatToolButton { objectName: "petPreviewAction"; theme: panel.theme; text: qsTranslate("Launcher", "Поиграть"); onClicked: { panel.controller.interact(); demoPet.interact() } }
        ChatToolButton { objectName: "petRecenterButton"; theme: panel.theme; text: qsTranslate("Launcher", "Вернуть на экран"); visible: panel.controller.canReposition; enabled: panel.controller.running; onClicked: panel.controller.resetPosition() }
        Item { Layout.fillWidth: true }
        ChatToolButton { theme: panel.theme; text: "100%"; enabled: panel.controller.sizePercent !== 100; onClicked: panel.controller.setSizePercent(100); Accessible.name: qsTranslate("Launcher", "Сбросить размер") }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Анимации"); color: panel.theme.ink; font.pixelSize: 12 }
        UiSwitch { theme: panel.theme; checked: panel.controller.motion; onToggled: panel.controller.setMotion(checked) }
    }
    Text { Layout.fillWidth: true; text: panel.controller.busy ? qsTranslate("Launcher", "Готовлю отдельное окно…") : qsTranslate("Launcher", "Правый клик — скрыть или открыть мини-чат. Ctrl + колесо — размер."); color: panel.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
    UiNotice { theme: panel.theme; text: panel.controller.error; error: true; Layout.fillWidth: true }
}
