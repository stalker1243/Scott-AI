import QtQuick
import QtQuick.Controls

MenuItem {
    id: item
    required property QtObject theme
    implicitHeight: 36; implicitWidth: 174
    leftPadding: 12; rightPadding: 12
    font.family: theme.fontFamily; font.pixelSize: 13
    background: Rectangle {
        radius: item.theme.controlRadius
        color: item.highlighted || item.hovered ? Qt.alpha(item.theme.accent, 0.13) : "transparent"
        border.color: item.visualFocus ? item.theme.accent : "transparent"
    }
    contentItem: Text { text: item.text; font: item.font; color: item.enabled ? item.theme.ink : item.theme.muted; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
}
