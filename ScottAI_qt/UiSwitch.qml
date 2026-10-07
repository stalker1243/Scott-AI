import QtQuick
import QtQuick.Controls

Switch {
    id: control
    required property QtObject theme
    hoverEnabled: true; spacing: 12; padding: 6
    implicitHeight: Math.max(42, contentItem.implicitHeight + topPadding + bottomPadding)
    font.family: theme.fontFamily
    opacity: enabled ? 1 : 0.45
    Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 150 } }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    indicator: Rectangle {
        implicitWidth: 40; implicitHeight: 24
        x: control.leftPadding; y: (control.height - height) / 2
        radius: 12; color: control.checked ? control.theme.accent : control.theme.elevated
        border.color: control.visualFocus ? control.theme.ink : control.checked ? control.theme.accent : control.theme.line
        Behavior on color { enabled: control.theme.motion; ColorAnimation { duration: 160 } }
        Rectangle {
            anchors.fill: parent; anchors.margins: -3; radius: 15
            color: "transparent"; border.color: control.theme.accent
            opacity: control.visualFocus ? 0.6 : control.hovered ? 0.25 : 0
            Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 140 } }
        }
        Rectangle {
            x: control.checked ? 19 : 3; y: 3; width: 18; height: 18; radius: 9
            color: control.checked ? control.theme.accentText : control.theme.muted
            Behavior on x { enabled: control.theme.motion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        }
    }
    contentItem: Text {
        text: control.text; color: control.theme.ink; font: control.font
        wrapMode: Text.Wrap
        leftPadding: control.indicator.width + control.spacing; verticalAlignment: Text.AlignVCenter
    }
}
