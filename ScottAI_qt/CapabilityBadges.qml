import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "CapabilityInfo.js" as CapabilityInfo

Flow {
    id: badges
    required property QtObject theme
    property var capabilities: ({})
    signal featureRequested(string feature)
    spacing: 5
    Repeater {
        model: [{key:"documents", name:"Файлы"}, {key:"images", name:"Фото"}, {key:"video", name:"Видео"}, {key:"image_generation", name:"Генерация"}]
        delegate: Rectangle {
            required property var modelData
            readonly property bool supported: badges.capabilities[modelData.key] === true
            width: badgeLabel.implicitWidth + 16; height: 24; radius: 7
            color: supported ? Qt.rgba(badges.theme.accent.r, badges.theme.accent.g, badges.theme.accent.b, 0.14) : badges.theme.elevated
            border.color: supported ? badges.theme.accent : badges.theme.line
            ToolTip.visible: mouse.containsMouse
            ToolTip.delay: 350
            ToolTip.text: CapabilityInfo.description(badges.capabilities, modelData.key)
            MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: badges.featureRequested(modelData.key) }
            Text {
                id: badgeLabel; anchors.centerIn: parent
                text: modelData.name + (supported ? " ✓" : " —")
                color: supported ? badges.theme.accent : badges.theme.muted
                font.family: badges.theme.fontFamily; font.pixelSize: 10
            }
        }
    }
}
