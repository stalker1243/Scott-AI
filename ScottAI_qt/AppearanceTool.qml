import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

Button {
    id: button
    required property QtObject theme
    property string glyph: "reset"
    property bool selected: false
    implicitWidth: 34; implicitHeight: 32
    hoverEnabled: true
    Accessible.name: text
    Accessible.checked: selected
    ToolTip.visible: hovered || visualFocus
    ToolTip.delay: 400
    ToolTip.text: text
    onClicked: if (glyph === "info") ToolTip.show(text, 5000)
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    background: Rectangle {
        radius: 8
        color: button.selected ? Qt.alpha(button.theme.accent, 0.12) : button.hovered ? button.theme.elevated : "transparent"
        border.color: button.visualFocus ? button.theme.accent : button.selected ? Qt.alpha(button.theme.accent, 0.3) : "transparent"
        Behavior on color { enabled: button.theme.motion; ColorAnimation { duration: 140 } }
    }
    contentItem: Item {
        readonly property color tone: button.selected ? button.theme.accent : button.theme.muted
        ScottMark { visible: button.glyph === "logo"; anchors.centerIn: parent; width: 15; height: 18; color: button.contentItem.tone }
        Shape {
            visible: button.glyph !== "logo"
            anchors.centerIn: parent; width: 20; height: 20
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: "transparent"; strokeColor: button.contentItem.tone; strokeWidth: 1.5
                capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                PathSvg { path: button.glyph === "close" ? "M5 5 L15 15 M15 5 L5 15"
                    : button.glyph === "motion" ? "M7 4 L15 10 L7 16 Z M3 7 L3 13"
                    : button.glyph === "sun" ? "M10 6 A4 4 0 1 1 10 14 A4 4 0 1 1 10 6 M10 1 L10 3 M10 17 L10 19 M1 10 L3 10 M17 10 L19 10 M3.5 3.5 L5 5 M15 15 L16.5 16.5 M3.5 16.5 L5 15 M15 5 L16.5 3.5"
                    : button.glyph === "moon" ? "M13 2 A8 8 0 1 0 18 13 A7 7 0 0 1 13 2 Z"
                    : button.glyph === "info" ? "M10 2 A8 8 0 1 1 10 18 A8 8 0 1 1 10 2 M10 9 L10 14 M10 6 L10 6.1"
                    : "M4 9 A6 6 0 1 1 5 14 M4 4 L4 9 L9 9" }
            }
        }
    }
}
