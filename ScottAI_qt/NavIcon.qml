import QtQuick
import QtQuick.Shapes

Item {
    id: icon
    property int symbol: 0
    property color color: "white"
    implicitWidth: 24
    implicitHeight: 24
    readonly property var paths: [
        "M3 10 L12 3 L21 10 M5 9 L5 21 L10 21 L10 14 L14 14 L14 21 L19 21 L19 9",
        "M5 4 L19 4 Q21 4 21 6 L21 15 Q21 17 19 17 L10 17 L5 21 L5 17 Q3 17 3 15 L3 6 Q3 4 5 4 M7 8 L17 8 M7 12 L14 12",
        "M5 4 L19 4 Q21 4 21 6 L21 16 Q21 18 19 18 L5 18 Q3 18 3 16 L3 6 Q3 4 5 4 M8 21 L16 21 M12 18 L12 21 M6 12 L9 12 L11 8 L14 15 L16 11 L18 11",
        "M12 3 A9 9 0 1 1 12 21 A9 9 0 1 1 12 3 M12 3 L12 21 M12 7 L16 7 M12 11 L18 11 M12 15 L17 15",
        "M12 3 L21 8 L21 16 L12 21 L3 16 L3 8 Z M3 8 L12 13 L21 8 M12 13 L12 21 M7.5 5.5 L16.5 10.5",
        "M17 10 A7 7 0 1 1 3 10 A7 7 0 1 1 17 10 M15 15 L21 21",
        "M6 9 L12 15 L18 9",
        "M4 6 L20 6 M4 12 L20 12 M4 18 L20 18 M9 3 L9 9 M16 9 L16 15 M8 15 L8 21",
        "M16 7 A4 4 0 1 1 8 7 A4 4 0 1 1 16 7 M4 21 L4 19 Q4 14 12 14 Q20 14 20 19 L20 21",
        "M13 3 L5 13 L11 13 L10 21 L19 10 L13 10 Z",
        "M4 5 L7 5 L7 9 L4 9 Z M11 7 L21 7 M4 15 L7 15 L7 19 L4 19 Z M11 17 L21 17 M5.5 9 L5.5 15",
        "M7 6 L17 6 Q18 6 18 7 L18 17 Q18 18 17 18 L7 18 Q6 18 6 17 L6 7 Q6 6 7 6 M9 9 L15 9 L15 15 L9 15 Z M9 3 L9 6 M15 3 L15 6 M9 18 L9 21 M15 18 L15 21 M3 9 L6 9 M3 15 L6 15 M18 9 L21 9 M18 15 L21 15"
    ]
    Shape {
        width: 24; height: 24
        preferredRendererType: Shape.CurveRenderer
        transform: Scale { xScale: icon.width / 24; yScale: icon.height / 24 }
        ShapePath {
            strokeColor: icon.color; strokeWidth: 1.65; fillColor: "transparent"
            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            PathSvg { path: icon.paths[icon.symbol] || icon.paths[0] }
        }
    }
}
