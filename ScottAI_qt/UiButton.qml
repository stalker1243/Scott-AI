import QtQuick
import QtQuick.Controls

Button {
    id: control
    required property QtObject theme
    property bool primary: false
    property bool destructive: false
    readonly property color accent: destructive ? (primary ? "#b34a38" : theme.danger) : theme.accent
    implicitHeight: 44; leftPadding: 18; rightPadding: 18
    font.pixelSize: 14
    font.family: theme.fontFamily
    hoverEnabled: true
    opacity: enabled ? 1 : 0.45
    scale: down ? 0.97 : 1
    Behavior on scale { enabled: control.theme.motion; NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
    Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 150 } }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    background: Rectangle {
        radius: control.theme.controlRadius
        color: control.primary ? (control.down ? Qt.darker(control.accent, 1.12) : control.hovered ? Qt.lighter(control.accent, 1.12) : control.accent)
                               : control.hovered ? control.theme.elevated : control.theme.surface
        border.color: control.activeFocus || control.primary || control.hovered ? control.accent : control.theme.line
        Behavior on color { enabled: control.theme.motion; ColorAnimation { duration: 150 } }
        Behavior on border.color { enabled: control.theme.motion; ColorAnimation { duration: 150 } }
        Behavior on radius { enabled: control.theme.motion; NumberAnimation { duration: 220 } }
        Rectangle {
            anchors.fill: parent; anchors.margins: -3
            radius: parent.radius + 3; color: "transparent"; border.color: control.accent
            opacity: control.visualFocus ? 0.45 : 0
            Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 150 } }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: 1; radius: Math.max(0, parent.radius - 1)
            color: control.primary ? "white" : control.accent; opacity: control.down ? 0.10 : 0
            Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 100 } }
        }
    }
    contentItem: Text {
        text: control.text; color: control.primary ? (control.destructive ? "white" : control.theme.accentText) : control.destructive ? control.accent : control.theme.ink
        font.family: control.font.family; font.pixelSize: control.font.pixelSize; font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
    }
}
