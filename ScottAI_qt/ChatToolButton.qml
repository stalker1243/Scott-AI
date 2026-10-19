import QtQuick
import QtQuick.Controls

Button {
    id: control
    required property QtObject theme
    implicitHeight: 32
    leftPadding: 10; rightPadding: 10
    hoverEnabled: true
    font.family: theme.fontFamily; font.pixelSize: 12
    Accessible.name: text
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    background: Rectangle {
        radius: control.theme.controlRadius
        color: control.down ? Qt.alpha(control.theme.accent, 0.16) : control.hovered ? control.theme.elevated : "transparent"
        border.color: control.visualFocus ? control.theme.accent : "transparent"
        Behavior on color { enabled: control.theme.motion; ColorAnimation { duration: 140 } }
    }
    contentItem: Text {
        text: control.text; color: control.enabled ? control.theme.muted : Qt.alpha(control.theme.muted, 0.5)
        font: control.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
    }
}
