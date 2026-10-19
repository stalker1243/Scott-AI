import QtQuick

Rectangle {
    id: panel
    required property QtObject theme
    property bool flat: false
    radius: flat ? 0 : theme.cardRadius
    color: flat ? "transparent" : theme.surface
    border.color: flat ? "transparent" : theme.line
    Behavior on radius { enabled: panel.theme.motion && panel.visible; NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
    Rectangle { visible: panel.flat; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: panel.theme.line }
    Rectangle {
        anchors.fill: parent; anchors.margins: 1; radius: Math.max(0, panel.radius - 1)
        visible: opacity > 0; opacity: !panel.flat && panel.theme.decoration === "glass" ? (1 - panel.theme.panelTransparency / 100) * panel.theme.glassOpacity : 0
        gradient: Gradient {
            GradientStop { position: 0; color: panel.theme.dark ? "#20ffffff" : "#70ffffff" }
            GradientStop { position: 0.55; color: "#00ffffff" }
        }
        Behavior on opacity { enabled: panel.theme.motion; NumberAnimation { duration: 220 } }
    }
}
