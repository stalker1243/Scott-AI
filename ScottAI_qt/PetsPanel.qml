import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "PetCatalog.js" as Pets

ColumnLayout {
    id: panel
    required property QtObject theme
    required property var controller
    readonly property var selected: Pets.find(controller.kind)
    spacing: 10
    Rectangle {
        Layout.fillWidth: true; implicitHeight: 196; radius: 13; clip: true
        color: Qt.alpha(panel.theme.elevated, 0.45); border.color: panel.theme.line
        Rectangle { anchors.centerIn: parent; width: 170; height: 170; radius: 85; color: Qt.alpha(Pets.color(panel.controller.variant), 0.045); border.color: Qt.alpha(Pets.color(panel.controller.variant), 0.08) }
        Button {
            objectName: "petChoice0"; x: 12; y: 6; padding: 0; implicitHeight: 28
            text: qsTranslate("Launcher", panel.selected.name)
            Accessible.name: text; hoverEnabled: true
            onClicked: panel.controller.selectPet(panel.selected.id)
            background: Rectangle { radius: 5; color: "transparent"; border.color: parent.visualFocus ? panel.theme.accent : "transparent" }
            contentItem: Text { text: parent.text; color: panel.theme.ink; font.family: panel.theme.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold; verticalAlignment: Text.AlignVCenter }
        }
        PetCharacter {
            id: demoPet; objectName: "petLargePreview"
            anchors.centerIn: parent
            width: 182; height: 182
            kind: panel.controller.kind; variant: panel.controller.variant
            motion: panel.theme.motion && panel.controller.motion; demo: true
        }
        Column {
            anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Repeater {
                model: panel.selected.colors
                Button {
                    id: swatch
                    required property string modelData
                    objectName: "petColor_" + modelData
                    implicitWidth: 30; implicitHeight: 30; hoverEnabled: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.checked: panel.controller.variant === modelData
                    Accessible.name: qsTranslate("Launcher", Pets.colorNames[modelData])
                    ToolTip.visible: hovered; ToolTip.text: Accessible.name
                    onClicked: panel.controller.selectVariant(modelData)
                    background: Rectangle { anchors.fill: parent; anchors.margins: 3; radius: 12; color: Pets.color(swatch.modelData); border.width: panel.controller.variant === swatch.modelData || swatch.visualFocus ? 2 : 0; border.color: panel.theme.ink }
                    contentItem: Item {}
                }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "На рабочем столе"); color: panel.theme.ink; font.pixelSize: 13 }
        UiSwitch { objectName: "desktopPetToggle"; theme: panel.theme; checked: panel.controller.enabled; enabled: !panel.controller.busy; Accessible.name: qsTranslate("Launcher", "На рабочем столе"); onToggled: panel.controller.setEnabled(checked) }
    }
    ColumnLayout {
        Layout.fillWidth: true; spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Размер"); color: panel.theme.muted; font.pixelSize: 12 }
            Text { text: panel.controller.sizePercent + "%"; color: panel.theme.ink; font.pixelSize: 12 }
        }
        UiSlider { objectName: "petSizeSlider"; theme: panel.theme; Layout.fillWidth: true; from: 50; to: 200; stepSize: 5; value: panel.controller.sizePercent; Accessible.name: qsTranslate("Launcher", "Размер питомца"); onMoved: panel.controller.setSizePercent(Math.round(value)) }
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 4
        ChatToolButton { objectName: "petPreviewAction"; theme: panel.theme; text: qsTranslate("Launcher", "Поиграть"); onClicked: { panel.controller.interact(); demoPet.interact() } }
        ChatToolButton { objectName: "petRecenterButton"; theme: panel.theme; text: qsTranslate("Launcher", "Вернуть на экран"); visible: panel.controller.canReposition; enabled: panel.controller.running; onClicked: panel.controller.resetPosition() }
        Item { Layout.fillWidth: true }
        ChatToolButton { theme: panel.theme; text: "100%"; enabled: panel.controller.sizePercent !== 100; onClicked: panel.controller.setSizePercent(100); Accessible.name: qsTranslate("Launcher", "Сбросить размер") }
        AppearanceTool { objectName: "petMotion"; theme: panel.theme; glyph: "motion"; text: qsTranslate("Launcher", "Анимации"); selected: panel.controller.motion; Accessible.role: Accessible.CheckBox; onClicked: panel.controller.setMotion(!panel.controller.motion) }
        AppearanceTool { theme: panel.theme; glyph: "info"; text: qsTranslate("Launcher", "Правый клик — скрыть или открыть мини-чат. Ctrl + колесо — размер.") }
    }
    UiNotice { theme: panel.theme; text: panel.controller.busy ? qsTranslate("Launcher", "Готовлю отдельное окно…") : ""; Layout.fillWidth: true }
    UiNotice { theme: panel.theme; text: panel.controller.error; error: true; Layout.fillWidth: true }
}
