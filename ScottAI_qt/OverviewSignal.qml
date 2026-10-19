import QtQuick

Item {
    id: signal
    required property QtObject theme
    property bool online: false
    property bool active: false
    property bool animate: true
    property real phase: 0
    readonly property color tone: online ? theme.accent : theme.muted
    Accessible.role: Accessible.Graphic
    Accessible.name: "ScottAI"
    NumberAnimation on phase {
        from: 0; to: Math.PI * 2; duration: signal.active ? 3600 : 8400
        loops: Animation.Infinite; running: signal.visible && signal.animate
    }
    Repeater {
        model: 3
        Rectangle {
            required property int index
            anchors.centerIn: parent
            width: signal.width * (0.62 + index * 0.18); height: width; radius: width / 2
            color: Qt.alpha(signal.tone, index === 0 ? 0.07 : 0.015)
            border.color: Qt.alpha(signal.tone, 0.13 - index * 0.025)
            scale: signal.animate ? 1 + Math.sin(signal.phase - index * 0.7) * (signal.active ? 0.035 : 0.012) : 1
        }
    }
    Image {
        anchors.centerIn: parent; width: signal.width * 0.31; height: width
        source: signal.theme.dark ? "qrc:/brand/scott-logo.png" : "qrc:/brand/scott-logo-light.png"
        fillMode: Image.PreserveAspectFit; smooth: true; opacity: signal.online ? 1 : 0.5
        Behavior on opacity { enabled: signal.animate; NumberAnimation { duration: 250 } }
    }
    Repeater {
        model: 28
        Rectangle {
            required property int index
            readonly property real angle: index * Math.PI * 2 / 28
            readonly property real energy: signal.active && signal.animate ? (1 + Math.sin(signal.phase * 2 + index * 0.73)) / 2 : 0
            width: 2; height: 3 + energy * 8; radius: 1
            x: signal.width / 2 + Math.cos(angle) * signal.width * 0.46 - width / 2
            y: signal.height / 2 + Math.sin(angle) * signal.height * 0.46 - height / 2
            rotation: index * 360 / 28 + 90
            color: signal.tone; opacity: 0.2 + energy * 0.65
        }
    }
}
