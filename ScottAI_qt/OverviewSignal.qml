import QtQuick

Item {
    id: signal
    required property QtObject theme
    property bool online: false
    property bool active: false
    property bool animate: true
    property real inputLevel: 0
    property real energy: animate && active ? Math.max(0, Math.min(1, inputLevel)) : 0
    Behavior on energy { NumberAnimation { duration: 95; easing.type: Easing.OutCubic } }
    property real phase: 0
    readonly property color tone: online ? theme.accent : theme.muted
    Accessible.role: Accessible.Graphic
    Accessible.name: "ScottAI"
    NumberAnimation on phase {
        from: 0; to: Math.PI * 2; duration: 4200
        loops: Animation.Infinite; running: signal.visible && signal.animate && signal.active
    }
    Repeater {
        model: 2
        Rectangle {
            required property int index
            anchors.centerIn: parent
            width: signal.width * (0.79 + index * 0.18); height: width; radius: width / 2
            color: Qt.alpha(signal.tone, index === 0 ? 0.045 : 0.008)
            border.color: Qt.alpha(signal.tone, index === 0 ? 0.09 : 0.05)
            scale: signal.active && signal.animate ? 1 + Math.sin(signal.phase - index * 0.8) * 0.025 + signal.energy * 0.13 : 1
        }
    }
    ScottMark {
        objectName: "overviewBrandMark"
        anchors.centerIn: parent; width: signal.width * 0.56; height: signal.height * 0.58
        color: signal.online ? signal.theme.ink : signal.theme.muted
        opacity: signal.online ? 1 : 0.55
        scale: signal.active && signal.animate ? 1 + Math.sin(signal.phase) * 0.012 : 1
        Behavior on opacity { enabled: signal.animate; NumberAnimation { duration: 250 } }
    }
    Repeater {
        model: 5
        Rectangle {
            required property int index
            readonly property real energy: signal.animate ? (1 + Math.sin(signal.phase * 2 + index * 0.9)) / 2 : 0.4
            visible: signal.active
            width: 3; height: 3 + signal.energy * (12 + energy * 15); radius: 1.5
            x: signal.width / 2 + (index - 2) * 7 - width / 2
            y: signal.height * 0.9 - height / 2
            color: signal.tone; opacity: 0.35 + signal.energy * 0.65
        }
    }
}
