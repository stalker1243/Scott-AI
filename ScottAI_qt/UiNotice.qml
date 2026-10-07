import QtQuick

Rectangle {
    id: notice
    required property QtObject theme
    property string text: ""
    property bool error: false
    property bool warning: false
    property string displayedText: ""
    property real reveal: text.length > 0 ? 1 : 0
    readonly property color tone: error ? theme.danger : warning ? (theme.dark ? "#e9c27b" : "#865800") : theme.success
    onTextChanged: if (text.length > 0) displayedText = text
    Component.onCompleted: if (text.length > 0) displayedText = text
    implicitHeight: (label.implicitHeight + 28) * reveal
    visible: reveal > 0; opacity: reveal; clip: true
    radius: theme.controlRadius; color: Qt.alpha(tone, 0.08); border.color: Qt.alpha(tone, 0.28)
    Behavior on reveal { enabled: notice.theme.motion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    Rectangle { x: 12; y: 17; width: 6; height: 6; radius: 3; color: notice.tone }
    Text {
        id: label
        x: 28; y: 14; width: parent.width - 42
        text: notice.displayedText; textFormat: Text.PlainText; wrapMode: Text.Wrap
        color: notice.tone; font.pixelSize: 12; font.family: notice.theme.fontFamily
    }
}
