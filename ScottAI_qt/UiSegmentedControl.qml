import QtQuick
import QtQuick.Controls

Control {
    id: control
    required property QtObject theme
    property var model: []
    property int currentIndex: 0
    signal activated(int index)
    padding: 4
    implicitWidth: model.length * 120 + 8
    implicitHeight: 48

    function select(index) {
        if (index < 0 || index >= model.length) return
        activated(index)
        const button = options.itemAt(index)
        if (button) button.forceActiveFocus(Qt.TabFocusReason)
    }
    background: Rectangle {
        radius: control.theme.controlRadius + 4
        color: Qt.alpha(control.theme.elevated, 0.6)
        border.color: control.theme.line
    }
    contentItem: Item {
        Rectangle {
            x: control.currentIndex * width
            width: parent.width / Math.max(1, control.model.length)
            height: parent.height; radius: control.theme.controlRadius
            color: Qt.alpha(control.theme.accent, 0.16)
            border.color: Qt.alpha(control.theme.accent, 0.3)
            visible: control.model.length > 0
            Behavior on x { enabled: control.theme.motion; NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        }
        Row {
            anchors.fill: parent
            Repeater {
                id: options
                model: control.model
                Button {
                    id: option
                    required property int index
                    required property string modelData
                    objectName: control.objectName + "Option" + index
                    width: control.availableWidth / Math.max(1, control.model.length)
                    height: control.availableHeight
                    text: modelData; hoverEnabled: true
                    checked: control.currentIndex === index
                    Accessible.role: Accessible.PageTab
                    Accessible.checked: checked
                    onClicked: control.activated(index)
                    Keys.onLeftPressed: control.select(Math.max(0, index - 1))
                    Keys.onRightPressed: control.select(Math.min(control.model.length - 1, index + 1))
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Home) { control.select(0); event.accepted = true }
                        else if (event.key === Qt.Key_End) { control.select(control.model.length - 1); event.accepted = true }
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    background: Rectangle {
                        radius: control.theme.controlRadius
                        color: option.down ? Qt.alpha(control.theme.accent, 0.10) : option.hovered && !option.checked ? Qt.alpha(control.theme.accent, 0.06) : "transparent"
                        border.color: option.visualFocus ? control.theme.accent : "transparent"
                        Behavior on color { enabled: control.theme.motion; ColorAnimation { duration: 120 } }
                    }
                    contentItem: Text {
                        text: option.text; color: option.checked ? control.theme.accent : control.theme.muted
                        font.family: control.theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        scale: option.down ? 0.96 : 1
                        Behavior on color { enabled: control.theme.motion; ColorAnimation { duration: 150 } }
                        Behavior on scale { enabled: control.theme.motion; NumberAnimation { duration: 120 } }
                    }
                }
            }
        }
    }
}
