import QtQuick
import QtQuick.Controls

Slider {
    id: control
    required property QtObject theme
    from: 0; to: 100; stepSize: 1; implicitHeight: 36
    hoverEnabled: true
    opacity: enabled ? 1 : 0.45
    Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 150 } }
    background: Rectangle {
        x: control.leftPadding; y: (control.height - height) / 2
        width: control.availableWidth; height: 5; radius: 3; color: control.theme.elevated
        Rectangle { width: control.visualPosition * parent.width; height: parent.height; radius: 3; color: control.theme.accent }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2
        width: 18; height: 18; radius: 9
        color: control.theme.accent; border.color: control.theme.ink
        scale: control.pressed ? 1.15 : control.hovered && control.enabled ? 1.06 : 1
        Behavior on scale { enabled: control.theme.motion; NumberAnimation { duration: 120 } }
        Rectangle {
            anchors.fill: parent; anchors.margins: -5; radius: 14
            color: Qt.alpha(control.theme.accent, 0.1); border.color: control.theme.accent
            opacity: control.visualFocus ? 0.5 : control.pressed ? 0.35 : control.hovered && control.enabled ? 0.2 : 0
            Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 140 } }
        }
    }
}
