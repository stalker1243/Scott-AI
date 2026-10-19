import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "StyleCatalog.js" as Styles

Popup {
    id: panel
    objectName: "appearancePopup"
    required property QtObject theme
    required property var host
    required property var companions
    property int section: 0
    implicitWidth: Math.min(section === 1 ? 430 : 358, host.width - 32)
    implicitHeight: Math.min(body.implicitHeight + 32, host.height - 64)
    width: implicitWidth
    height: Math.min(body.implicitHeight + topPadding + bottomPadding, host.height - 64)
    contentWidth: width - leftPadding - rightPadding
    contentHeight: height - topPadding - bottomPadding
    x: Math.min(host.navigationWidth + 16, host.width - width - 16)
    y: host.height - height - 16
    padding: 16; focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: panel.theme.motion ? 150 : 0 } }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: panel.theme.motion ? 100 : 0 } }
    background: Rectangle { color: panel.theme.popup; radius: 16; border.color: panel.theme.line }
    contentItem: ScrollView {
        id: viewport
        contentWidth: availableWidth; clip: true
        ColumnLayout {
            id: body
            width: viewport.availableWidth; spacing: 14
            Text { text: qsTranslate("Launcher", "Персонализация"); color: panel.theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold }
            UiSegmentedControl { objectName: "personalizationTabs"; theme: panel.theme; Layout.fillWidth: true; implicitHeight: 38; model: [qsTranslate("Launcher", "Интерфейс"), qsTranslate("Launcher", "Питомцы")]; currentIndex: panel.section; onActivated: function(index) { panel.section = index } }
            ColumnLayout {
            visible: panel.section === 0; Layout.fillWidth: true; spacing: 14
            RowLayout {
                Layout.fillWidth: true; spacing: 8
                Repeater {
                    model: Styles.styles
                    delegate: Button {
                        id: style
                        required property var modelData
                        required property int index
                        objectName: "appearanceStyle" + index
                        readonly property var previewPalette: Styles.palette(modelData, panel.host.darkMode)
                        readonly property bool chosen: panel.host.styleId === modelData.id
                        Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 104; padding: 7; hoverEnabled: true
                        Accessible.name: modelData.name
                        onClicked: { panel.host.styleId = modelData.id; panel.host.persist() }
                        background: Rectangle {
                            radius: 10; color: style.chosen ? Qt.alpha(panel.theme.accent, 0.10) : "transparent"
                            border.color: style.chosen || style.visualFocus ? panel.theme.accent : panel.theme.line
                        }
                        contentItem: ColumnLayout {
                            spacing: 7
                            Rectangle {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                radius: style.modelData.decoration === "terminal" ? 2 : 6
                                color: style.previewPalette.bg; clip: true
                                Rectangle { width: parent.width * 0.23; height: parent.height; color: style.previewPalette.sidebar
                                    Column { x: 4; y: 9; spacing: 5
                                        Repeater { model: 3; Rectangle { width: 7; height: 3; radius: 1; color: style.previewPalette.accent } }
                                    }
                                }
                                Column {
                                    x: parent.width * 0.31; y: 10; width: parent.width * 0.59; spacing: 5
                                    Rectangle { width: parent.width; height: 4; radius: 2; color: style.previewPalette.ink; opacity: 0.8 }
                                    Rectangle { width: parent.width * 0.7; height: 3; radius: 2; color: style.previewPalette.muted }
                                    Rectangle { width: parent.width; height: 13; radius: 3; color: style.previewPalette.elevated
                                        Rectangle { width: 5; height: 5; radius: 2; color: style.previewPalette.accent; anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                }
                            }
                            Text { Layout.fillWidth: true; text: qsTranslate("Launcher", style.modelData.name); color: panel.theme.ink; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight }
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 8
                Repeater {
                    model: [true, false]
                    delegate: Button {
                        required property bool modelData
                        objectName: modelData ? "appearanceDark" : "appearanceLight"
                        text: modelData ? qsTranslate("Launcher", "Тёмная") : qsTranslate("Launcher", "Светлая")
                        Accessible.name: text + qsTranslate("Launcher", " тема")
                        Layout.fillWidth: true; implicitHeight: 36; hoverEnabled: true
                        onClicked: { panel.host.darkMode = modelData; panel.host.persist() }
                        background: Rectangle { radius: 8; color: modelData ? "#151a23" : "#f1f4f9"; border.color: panel.host.darkMode === modelData ? panel.theme.accent : panel.theme.line }
                        contentItem: Text { text: parent.text; color: parent.modelData ? "#edf2fb" : "#172238"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                }
            }
            Text { text: qsTranslate("Launcher", "Акцент"); color: panel.theme.muted; font.pixelSize: 12 }
            RowLayout {
                Layout.fillWidth: true; spacing: 9
                Repeater {
                    model: ["", "#5588ff", "#b078f5", "#248866", "#b87324", "#cb5967", "#168591"]
                    delegate: Button {
                        id: swatch
                        required property string modelData
                        required property int index
                        objectName: "appearanceAccent" + index
                        Accessible.name: modelData.length ? qsTranslate("Launcher", "Акцент ") + modelData : qsTranslate("Launcher", "Акцент по стилю")
                        ToolTip.visible: hovered; ToolTip.text: Accessible.name
                        implicitWidth: 34; implicitHeight: 34; hoverEnabled: true
                        onClicked: { panel.host.accentOverride = modelData; panel.host.persist() }
                        background: Rectangle {
                            anchors.fill: parent; anchors.margins: 3; radius: 14
                            color: swatch.modelData.length ? swatch.modelData : panel.host.stylePalette.accent
                            border.width: panel.host.accentOverride === swatch.modelData || swatch.visualFocus ? 2 : 0
                            border.color: panel.theme.ink
                            Text { anchors.centerIn: parent; visible: !swatch.modelData.length; text: "A"; color: Styles.accentText(parent.color); font.pixelSize: 12 }
                        }
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: panel.host.glassActive ? qsTranslate("Launcher", "Матовость стекла") : qsTranslate("Launcher", "Прозрачность панелей"); color: panel.theme.muted; font.pixelSize: 12 }
                    Text { text: (panel.host.glassActive ? panel.host.glassFrost : panel.host.panelTransparency) + "%"; color: panel.theme.ink; font.pixelSize: 12 }
                }
                UiSlider {
                    objectName: "appearanceMaterialSlider"
                    theme: panel.theme; Layout.fillWidth: true
                    value: panel.host.glassActive ? panel.host.glassFrost : panel.host.panelTransparency
                    Accessible.name: panel.host.glassActive ? qsTranslate("Launcher", "Матовость стекла") : qsTranslate("Launcher", "Прозрачность панелей")
                    onMoved: {
                        if (panel.host.glassActive) panel.host.glassFrost = Math.round(value)
                        else panel.host.setPanelTransparency(value)
                        saveTimer.restart()
                    }
                }
            }
            ColumnLayout {
                visible: panel.host.glassActive; Layout.fillWidth: true; spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Прозрачность панелей"); color: panel.theme.muted; font.pixelSize: 12 }
                    Text { text: panel.host.panelTransparency + "%"; color: panel.theme.ink; font.pixelSize: 12 }
                }
                UiSlider { theme: panel.theme; Layout.fillWidth: true; value: panel.host.panelTransparency; Accessible.name: qsTranslate("Launcher", "Прозрачность панелей"); onMoved: { panel.host.setPanelTransparency(value); saveTimer.restart() } }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Анимации"); color: panel.theme.muted; font.pixelSize: 12 }
                UiSwitch { theme: panel.theme; checked: panel.host.animationsEnabled; onToggled: { panel.host.animationsEnabled = checked; panel.host.persist() } }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Светлый значок"); color: panel.theme.muted; font.pixelSize: 12 }
                UiSwitch { theme: panel.theme; checked: panel.host.lightIcon; onToggled: { panel.host.lightIcon = checked; panel.host.persist() } }
                ChatToolButton { theme: panel.theme; text: qsTranslate("Launcher", "Сбросить"); onClicked: panel.host.resetAppearance() }
            }
            }
            PetsPanel { objectName: "petsPanel"; visible: panel.section === 1; Layout.fillWidth: true; theme: panel.theme; controller: panel.companions }
        }
    }
    Timer { id: saveTimer; interval: 250; onTriggered: panel.host.persist() }
}
