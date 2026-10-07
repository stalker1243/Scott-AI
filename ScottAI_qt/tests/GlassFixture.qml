import QtQuick

Window {
    id: fixture
    required property var hostWindow
    property bool glassActive: hostWindow.glassActive
    property int glassFrost: hostWindow.glassFrost
    property bool darkMode: hostWindow.darkMode
    width: 320; height: 120
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    Rectangle {
        anchors.fill: parent
        color: Qt.alpha(fixture.darkMode ? "#0d1529" : "#e7edf8", 0.16 + 0.64 * fixture.glassFrost / 100)
        Text {
            x: 20; y: 14; text: "ScottAI · Glass"
            color: fixture.darkMode ? "#f2f7ff" : "#172b48"
            font.family: "Segoe UI"; font.pixelSize: 18; font.weight: Font.DemiBold
        }
    }
}
