import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: bar
    required property Window windowHost
    required property QtObject theme
    required property string logoSource
    property string pageTitle: ""
    property bool navigationExpanded: false
    property string statusText: ""
    property bool online: false
    signal toggleNavigation()
    height: 44
    function toggleMaximized() {
        windowHost.toggleMaximizedAnimated()
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: bar.theme.line; opacity: 0.65 }
    RowLayout {
        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 8; spacing: 10
        UiButton {
            objectName: "navigationToggle"
            theme: bar.theme; text: "☰"; implicitWidth: 34; implicitHeight: 30
            Accessible.name: bar.navigationExpanded ? "Свернуть навигацию" : "Раскрыть навигацию"
            ToolTip.visible: hovered; ToolTip.text: Accessible.name; ToolTip.delay: 350
            onClicked: bar.toggleNavigation()
        }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true
            Row {
                anchors.verticalCenter: parent.verticalCenter; spacing: 10
                Image { width: 24; height: 24; source: bar.logoSource; sourceSize: Qt.size(56, 56) }
                Text { text: "ScottAI"; color: bar.theme.ink; font.family: bar.theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold; height: 24; verticalAlignment: Text.AlignVCenter }
                Text { text: " / " + bar.pageTitle; color: bar.theme.muted; font.family: bar.theme.fontFamily; font.pixelSize: 13; height: 24; verticalAlignment: Text.AlignVCenter }
            }
            DragHandler { enabled: !bar.windowHost.geometryAnimating; target: null; onActiveChanged: if (active) bar.windowHost.startSystemMove() }
            TapHandler { onDoubleTapped: bar.toggleMaximized() }
        }
        Rectangle {
            width: 7; height: 7; radius: 4
            color: bar.online ? bar.theme.success : bar.theme.danger
            Accessible.name: bar.statusText
            HoverHandler { id: statusHover }
            ToolTip.visible: statusHover.hovered; ToolTip.text: bar.statusText
        }
        Repeater {
            model: ["Свернуть", "Развернуть", "Закрыть"]
            Button {
                id: captionButton
                required property int index
                required property string modelData
                objectName: ["windowMinimize", "windowMaximize", "windowClose"][index]
                Accessible.name: index === 1 && (bar.windowHost.presentationVisibility === Window.Maximized || bar.windowHost.presentationVisibility === Window.FullScreen) ? "Восстановить размер" : modelData
                implicitWidth: 34; implicitHeight: 30; hoverEnabled: true
                onClicked: {
                    if (index === 0) bar.windowHost.minimizeAnimated()
                    else if (index === 1) bar.toggleMaximized()
                    else bar.windowHost.close()
                }
                ToolTip.visible: hovered
                ToolTip.text: Accessible.name
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                background: Rectangle {
                    radius: bar.theme.controlRadius
                    color: captionButton.hovered || captionButton.down ? (captionButton.index === 2 ? Qt.alpha(bar.theme.danger, 0.18) : bar.theme.elevated) : "transparent"
                    border.color: captionButton.visualFocus ? bar.theme.accent : "transparent"
                    Behavior on color { enabled: bar.theme.motion; ColorAnimation { duration: 120 } }
                }
                contentItem: Item {
                    readonly property color tone: captionButton.index === 2 && captionButton.hovered ? bar.theme.danger : bar.theme.muted
                    Rectangle { visible: captionButton.index === 0; anchors.centerIn: parent; width: 12; height: 1.5; color: parent.tone }
                    Rectangle { visible: captionButton.index === 1; anchors.centerIn: parent; width: 11; height: 10; radius: 1; color: "transparent"; border.color: parent.tone }
                    Rectangle { visible: captionButton.index === 1 && (bar.windowHost.presentationVisibility === Window.Maximized || bar.windowHost.presentationVisibility === Window.FullScreen); x: parent.width / 2 - 3; y: parent.height / 2 - 7; width: 9; height: 9; color: "transparent"; border.color: parent.tone }
                    Rectangle { visible: captionButton.index === 2; anchors.centerIn: parent; width: 14; height: 1.5; rotation: 45; color: parent.tone }
                    Rectangle { visible: captionButton.index === 2; anchors.centerIn: parent; width: 14; height: 1.5; rotation: -45; color: parent.tone }
                }
            }
        }
    }
}
