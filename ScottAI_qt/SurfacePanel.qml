import QtQuick

Rectangle {
    id: panel
    required property QtObject theme
    radius: theme.cardRadius; color: theme.surface; border.color: theme.line
    Behavior on radius { enabled: panel.theme.motion; NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
    Rectangle {
        anchors.fill: parent; anchors.margins: 1; radius: Math.max(0, panel.radius - 1)
        visible: opacity > 0; opacity: panel.theme.decoration === "glass" ? (1 - panel.theme.panelTransparency / 100) * panel.theme.glassOpacity : 0
        gradient: Gradient {
            GradientStop { position: 0; color: panel.theme.dark ? "#20ffffff" : "#70ffffff" }
            GradientStop { position: 0.55; color: "#00ffffff" }
        }
        Behavior on opacity { enabled: panel.theme.motion; NumberAnimation { duration: 220 } }
    }
}
