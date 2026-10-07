import QtQuick
import QtQuick.Controls

ScrollBar {
    id: bar
    required property QtObject theme
    hoverEnabled: true; padding: 2; minimumSize: 0.08
    contentItem: Rectangle {
        implicitWidth: 6; implicitHeight: 6; radius: 3
        color: bar.pressed ? bar.theme.accent : bar.theme.muted
        opacity: bar.policy === ScrollBar.AlwaysOff || bar.size >= 1 ? 0 : bar.active || bar.hovered ? 0.75 : 0.22
        Behavior on opacity { enabled: bar.theme.motion; NumberAnimation { duration: 180 } }
        Behavior on color { enabled: bar.theme.motion; ColorAnimation { duration: 140 } }
    }
    background: Item {}
}
