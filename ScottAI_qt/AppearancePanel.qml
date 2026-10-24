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
    implicitWidth: Math.min(460, host.width - 32)
    implicitHeight: Math.min(content.implicitHeight + topPadding + bottomPadding, host.height - 64)
    width: implicitWidth; height: implicitHeight
    x: Math.min(host.navigationWidth + 16, host.width - width - 16)
    y: host.height - height - 16
    padding: 16; focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: panel.theme.motion ? 160 : 0 } }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: panel.theme.motion ? 100 : 0 } }
    background: Rectangle { color: panel.theme.popup; radius: 18; border.color: panel.theme.line }
    contentItem: ColumnLayout {
        id: content
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Персонализация"); color: panel.theme.ink; font.family: panel.theme.fontFamily; font.pixelSize: 16; font.weight: Font.DemiBold }
            AppearanceTool { objectName: "appearanceClose"; theme: panel.theme; glyph: "close"; text: qsTranslate("Launcher", "Закрыть"); onClicked: panel.close() }
        }
        UiSegmentedControl {
            objectName: "personalizationTabs"; theme: panel.theme
            Layout.fillWidth: true; implicitHeight: 36
            model: [qsTranslate("Launcher", "Интерфейс"), qsTranslate("Launcher", "Питомцы")]
            currentIndex: panel.section; onActivated: function(index) { panel.section = index }
        }
        ScrollView {
            id: viewport
            Layout.fillWidth: true; Layout.fillHeight: true
            implicitHeight: body.implicitHeight
            contentWidth: availableWidth; contentHeight: body.implicitHeight; clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical: UiScrollBar { theme: panel.theme }
            ColumnLayout {
                id: body
                width: viewport.availableWidth; spacing: 0
                ColumnLayout {
                    visible: panel.section === 0
                    Layout.fillWidth: true; spacing: 12
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        Repeater {
                            model: Styles.styles
                            AppearancePreview {
                                required property var modelData
                                required property int index
                                objectName: "appearanceStyle" + index
                                Layout.fillWidth: true; Layout.minimumWidth: 0
                                theme: panel.theme; definition: modelData
                                dark: panel.host.darkMode; chosen: panel.host.styleId === modelData.id
                                accentOverride: panel.host.accentOverride
                                onClicked: { panel.host.styleId = modelData.id; panel.host.persist() }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        AppearanceTool {
                            objectName: "appearanceDark"; theme: panel.theme; glyph: "moon"
                            text: qsTranslate("Launcher", "Тёмная") + qsTranslate("Launcher", " тема")
                            selected: panel.host.darkMode
                            Accessible.role: Accessible.RadioButton
                            onClicked: { panel.host.darkMode = true; panel.host.persist() }
                        }
                        AppearanceTool {
                            objectName: "appearanceLight"; theme: panel.theme; glyph: "sun"
                            text: qsTranslate("Launcher", "Светлая") + qsTranslate("Launcher", " тема")
                            selected: !panel.host.darkMode
                            Accessible.role: Accessible.RadioButton
                            onClicked: { panel.host.darkMode = false; panel.host.persist() }
                        }
                        Rectangle { Layout.leftMargin: 4; Layout.rightMargin: 4; width: 1; height: 20; color: panel.theme.line }
                        Repeater {
                            model: ["", "#5588ff", "#b078f5", "#248866", "#b87324", "#cb5967", "#168591"]
                            Button {
                                id: swatch
                                required property string modelData
                                required property int index
                                objectName: "appearanceAccent" + index
                                Layout.fillWidth: true; Layout.minimumWidth: 24; implicitWidth: 34; implicitHeight: 34
                                hoverEnabled: true
                                Accessible.role: Accessible.RadioButton
                                Accessible.checked: panel.host.accentOverride === modelData
                                Accessible.name: modelData.length ? qsTranslate("Launcher", "Акцент ") + modelData : qsTranslate("Launcher", "Акцент по стилю")
                                ToolTip.visible: hovered; ToolTip.delay: 400; ToolTip.text: Accessible.name
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                onClicked: { panel.host.accentOverride = modelData; panel.host.persist() }
                                background: Rectangle {
                                    anchors.centerIn: parent; width: Math.min(28, parent.width - 2); height: width; radius: width / 2
                                    color: swatch.modelData.length ? swatch.modelData : panel.host.stylePalette.accent
                                    border.width: panel.host.accentOverride === swatch.modelData || swatch.visualFocus ? 2 : 0
                                    border.color: panel.theme.ink
                                    scale: swatch.down ? 0.9 : swatch.hovered ? 1.08 : 1
                                    Behavior on scale { enabled: panel.theme.motion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                                    Text { anchors.centerIn: parent; text: !swatch.modelData.length ? "A" : "✓"; visible: !swatch.modelData.length || panel.host.accentOverride === swatch.modelData; color: Styles.accentText(parent.color); font.pixelSize: 11 }
                                }
                                contentItem: Item {}
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
                            objectName: "appearanceMaterialSlider"; theme: panel.theme; Layout.fillWidth: true
                            from: panel.host.glassActive ? 1 : 0
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
                        UiSlider { objectName: "appearancePanelSlider"; theme: panel.theme; Layout.fillWidth: true; value: panel.host.panelTransparency; Accessible.name: qsTranslate("Launcher", "Прозрачность панелей"); onMoved: { panel.host.setPanelTransparency(value); saveTimer.restart() } }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 4
                        AppearanceTool {
                            objectName: "appearanceMotion"; theme: panel.theme; glyph: "motion"
                            text: qsTranslate("Launcher", "Анимации"); selected: panel.host.animationsEnabled
                            Accessible.role: Accessible.CheckBox
                            onClicked: { panel.host.animationsEnabled = !panel.host.animationsEnabled; panel.host.persist() }
                        }
                        AppearanceTool {
                            objectName: "appearanceTrayIcon"; theme: panel.theme; glyph: "logo"
                            text: qsTranslate("Launcher", "Светлый значок"); selected: panel.host.lightIcon
                            Accessible.role: Accessible.CheckBox
                            onClicked: { panel.host.lightIcon = !panel.host.lightIcon; panel.host.persist() }
                        }
                        Item { Layout.fillWidth: true }
                        AppearanceTool { objectName: "appearanceReset"; theme: panel.theme; glyph: "reset"; text: qsTranslate("Launcher", "Сбросить оформление"); onClicked: panel.host.resetAppearance() }
                    }
                }
                PetsPanel { objectName: "petsPanel"; visible: panel.section === 1; Layout.fillWidth: true; theme: panel.theme; controller: panel.companions }
            }
        }
    }
    Timer { id: saveTimer; interval: 250; onTriggered: panel.host.persist() }
}
