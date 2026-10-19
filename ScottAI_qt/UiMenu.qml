import QtQuick
import QtQuick.Controls

Menu {
    id: menu
    required property QtObject theme
    popupType: Popup.Item
    padding: 6
    implicitWidth: Math.max(184, contentItem.implicitWidth + padding * 2)
    background: Rectangle { color: menu.theme.popup; radius: menu.theme.controlRadius + 2; border.color: menu.theme.line }
    delegate: UiMenuItem { theme: menu.theme }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: menu.theme.motion ? 120 : 0 } }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: menu.theme.motion ? 90 : 0 } }
}
