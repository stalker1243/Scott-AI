import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    required property QtObject theme
    implicitHeight: 42; hoverEnabled: true
    font.family: theme.fontFamily
    opacity: enabled ? 1 : 0.45
    Behavior on opacity { enabled: control.theme.motion; NumberAnimation { duration: 150 } }
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    contentItem: Text {
        text: control.displayText; color: control.theme.ink; font: control.font
        leftPadding: 12; rightPadding: 34; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
    }
    background: FieldSurface { theme: control.theme; focused: control.activeFocus || control.popup.visible; hovered: control.hovered }
    indicator: NavIcon {
        x: control.width - width - 12; y: (control.height - height) / 2
        width: 16; height: 16; symbol: 6; color: control.theme.muted
        rotation: control.popup.visible ? 180 : 0
        Behavior on rotation { enabled: control.theme.motion; NumberAnimation { duration: 150 } }
    }
    delegate: ItemDelegate {
        id: option
        required property int index
        required property var modelData
        readonly property bool chosen: control.currentIndex === index
        width: optionsList.width - (optionsList.contentHeight > optionsList.height ? 12 : 0); height: 40
        hoverEnabled: true
        highlighted: control.highlightedIndex === index
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        contentItem: Text {
            text: control.textRole.length > 0 ? modelData[control.textRole] : modelData
            color: option.highlighted || option.chosen ? control.theme.accent : control.theme.ink; font: control.font
            leftPadding: 8; rightPadding: 22; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        }
        background: Rectangle {
            radius: control.theme.controlRadius
            color: option.highlighted || option.hovered ? control.theme.elevated : "transparent"
            Behavior on color { enabled: control.theme.motion; ColorAnimation { duration: 100 } }
            Rectangle { x: parent.width - 14; anchors.verticalCenter: parent.verticalCenter; width: 5; height: 5; radius: 3; color: control.theme.accent; visible: option.chosen }
        }
    }
    popup: Popup {
        objectName: control.objectName + "Popup"
        y: control.height + 6; width: control.width; padding: 4
        implicitHeight: Math.min(260, contentItem.implicitHeight + 8)
        background: Rectangle { radius: control.theme.controlRadius; color: control.theme.popup; border.color: control.theme.line }
        contentItem: ListView {
            id: optionsList
            implicitHeight: contentHeight; clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: UiScrollBar { theme: control.theme }
        }
        enter: Transition { enabled: control.theme.motion; NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 130 } }
        exit: Transition { enabled: control.theme.motion; NumberAnimation { property: "opacity"; to: 0; duration: 90 } }
    }
}
