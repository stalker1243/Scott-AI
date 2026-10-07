import QtQuick

Rectangle {
    id: field
    required property QtObject theme
    property bool focused: false
    property bool hovered: false
    property bool invalid: false
    property color fill: theme.bg
    readonly property color highlight: invalid ? theme.danger : theme.accent
    radius: theme.controlRadius; color: fill
    border.color: focused || invalid ? highlight : hovered ? Qt.alpha(theme.accent, 0.55) : theme.line
    Behavior on border.color { enabled: field.theme.motion; ColorAnimation { duration: 160 } }
    Behavior on radius { enabled: field.theme.motion; NumberAnimation { duration: 220 } }
    Rectangle {
        anchors.fill: parent; anchors.margins: -3
        radius: field.radius + 3; color: "transparent"; border.width: 2; border.color: field.highlight
        opacity: field.focused ? 0.20 : 0
        Behavior on opacity { enabled: field.theme.motion; NumberAnimation { duration: 180 } }
    }
}
