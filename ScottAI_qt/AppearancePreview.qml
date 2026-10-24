import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "StyleCatalog.js" as Styles

Button {
    id: card
    required property QtObject theme
    required property var definition
    property bool dark: true
    property bool chosen: false
    property string accentOverride: ""
    readonly property var previewPalette: Styles.palette(definition, dark)
    readonly property color accent: accentOverride.length ? accentOverride : previewPalette.accent
    readonly property bool terminal: definition.decoration === "terminal"
    readonly property bool glass: definition.decoration === "glass"
    implicitWidth: 132; implicitHeight: 142
    padding: 7; hoverEnabled: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: qsTranslate("Launcher", definition.name)
    Accessible.description: qsTranslate("Launcher", definition.description)
    Accessible.checked: chosen
    ToolTip.visible: hovered
    ToolTip.delay: 500
    ToolTip.text: Accessible.description
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    scale: down ? 0.98 : 1
    Behavior on scale { enabled: card.theme.motion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    background: Rectangle {
        radius: 13
        color: card.chosen ? Qt.alpha(card.theme.accent, 0.08) : card.hovered ? Qt.alpha(card.theme.ink, 0.025) : "transparent"
        border.width: card.chosen || card.visualFocus ? 2 : 1
        border.color: card.chosen || card.visualFocus ? card.theme.accent : card.theme.line
        Behavior on color { enabled: card.theme.motion; ColorAnimation { duration: 150 } }
        Behavior on border.color { enabled: card.theme.motion; ColorAnimation { duration: 150 } }
    }
    contentItem: ColumnLayout {
        spacing: 10
        Rectangle {
            id: scene
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.minimumHeight: 88
            radius: card.terminal ? 3 : 8
            color: card.previewPalette.bg; clip: true
            border.color: Qt.alpha(card.previewPalette.ink, 0.1)
            Rectangle { visible: card.glass; x: parent.width * 0.45; y: -20; width: 95; height: 95; radius: 48; rotation: 25; color: Qt.alpha(card.accent, 0.17) }
            Rectangle { visible: card.glass; x: -12; y: 48; width: 80; height: 80; radius: 40; color: card.dark ? "#243658" : "#ccdcf7"; opacity: 0.5 }
            Rectangle {
                x: 1; y: 1; width: parent.width - 2; height: 13
                color: Qt.alpha(card.previewPalette.sidebar, card.glass ? 0.5 : 1)
                Row {
                    x: 5; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                    Repeater { model: 3; Rectangle { required property int index; width: 3; height: 3; radius: card.terminal ? 0 : 2; color: card.previewPalette.muted; opacity: index === 0 ? 0.6 : 0.25 } }
                }
                Rectangle { anchors.centerIn: parent; width: 22; height: 2; radius: 1; color: card.previewPalette.muted; opacity: 0.3 }
            }
            Rectangle {
                x: 1; y: 14; width: parent.width * 0.2; height: parent.height - 15
                color: Qt.alpha(card.previewPalette.sidebar, card.glass ? 0.5 : 1)
                Column {
                    anchors.horizontalCenter: parent.horizontalCenter; y: 10; spacing: 7
                    Repeater { model: 4; Rectangle { required property int index; width: 7; height: 4; radius: card.terminal ? 0 : 2; color: index === 0 ? card.accent : card.previewPalette.muted; opacity: index === 0 ? 1 : 0.35 } }
                }
            }
            Column {
                x: parent.width * 0.28; y: 24; width: parent.width * 0.62; spacing: 5
                ScottMark { anchors.horizontalCenter: parent.horizontalCenter; width: 27; height: 28; color: card.previewPalette.ink }
                Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 24; height: 3; radius: 1; color: card.previewPalette.ink; opacity: 0.6 }
                Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 38; height: 2; radius: 1; color: card.previewPalette.muted; opacity: 0.5 }
                Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 34; height: 9; radius: card.terminal ? 1 : 4; color: card.accent }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 2
            Text {
                Layout.fillWidth: true; Layout.minimumWidth: 0
                text: qsTranslate("Launcher", card.definition.name)
                font.family: card.theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold
                color: card.theme.ink; elide: Text.ElideRight
            }
            Rectangle {
                width: 14; height: 14; radius: 7
                color: card.chosen ? card.theme.accent : "transparent"
                border.color: card.chosen ? "transparent" : card.theme.line
                Text { anchors.centerIn: parent; text: "✓"; visible: card.chosen; color: card.theme.accentText; font.pixelSize: 10 }
            }
        }
    }
}
