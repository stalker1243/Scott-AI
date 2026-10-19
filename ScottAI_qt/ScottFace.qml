import QtQuick
import QtQuick.Shapes

// A small display with its own eyes, rather than a scaled sticker frame.
Item {
    id: face
    property color accent: "#68caff"
    property real gazeX: 0
    property real gazeY: 0
    property real blink: 1
    property real smile: 0
    property real surprise: 0
    property real sleepy: 0
    property real concentration: 0
    property real wink: 0
    readonly property real happy: Math.max(0, Math.min(1, (smile - 0.3) / 0.5)) * (1 - surprise)
    readonly property color light: Qt.lighter(accent, 1.5)

    Repeater {
        model: 2
        Item {
            id: eye
            required property int index
            objectName: "scottEye" + index
            width: 28; height: 34
            x: (index === 0 ? 0 : face.width - width) + face.gazeX * 3
            y: face.gazeY * 2 + (index === 0 ? -face.concentration : face.concentration) * 2
            rotation: (index === 0 ? -1 : 1) * (face.smile * 3 - face.concentration * 9)
            transform: Scale {
                origin.x: 14; origin.y: 17
                xScale: 1 + face.surprise * 0.1
                yScale: Math.max(0.06, face.blink * (1 - face.sleepy * 0.83 - (eye.index === 1 ? face.wink * 0.94 : 0)))
            }
            Item {
                width: 28; height: 34
                opacity: 1 - face.happy
                Rectangle { anchors.fill: parent; anchors.margins: -5; radius: 20; color: Qt.alpha(face.accent, 0.045) }
                Rectangle { anchors.fill: parent; anchors.margins: -2; radius: 18; color: Qt.alpha(face.accent, 0.13) }
                Rectangle {
                    width: 28; height: 34; radius: 14; border.width: 1; border.color: face.light
                    gradient: Gradient {
                        GradientStop { position: 0; color: face.light }
                        GradientStop { position: 0.5; color: face.accent }
                        GradientStop { position: 1; color: Qt.darker(face.accent, 1.15) }
                    }
                    Rectangle {
                        x: 9 + face.gazeX * 3; y: 5 + face.gazeY * 2; width: 15; height: 24; radius: 9
                        color: Qt.darker(face.accent, 1.23); opacity: 0.5
                    }
                    Rectangle { x: 4 + face.gazeX; y: 4 + face.gazeY; width: 9; height: 11; radius: 5; color: "#f0ffff" }
                    Rectangle { x: 20 + face.gazeX; y: 24 + face.gazeY; width: 4; height: 5; radius: 3; color: "#dbfaff"; opacity: 0.8 }
                    Rectangle { x: 4; y: 13; width: 2; height: 12; radius: 1; color: "#e4ffff"; opacity: 0.55 }
                }
            }
            Shape {
                opacity: face.happy
                ShapePath {
                    fillColor: "transparent"; strokeColor: Qt.alpha(face.accent, 0.1); strokeWidth: 13; capStyle: ShapePath.RoundCap
                    startX: 1; startY: 22
                    PathCubic { x: 27; y: 22; control1X: 5; control1Y: 5; control2X: 22; control2Y: 5 }
                }
                ShapePath {
                    fillColor: "transparent"; strokeColor: face.light; strokeWidth: 6; capStyle: ShapePath.RoundCap
                    startX: 1; startY: 22
                    PathCubic { x: 27; y: 22; control1X: 5; control1Y: 5; control2X: 22; control2Y: 5 }
                }
            }
            Shape {
                y: -9 - face.surprise * 5 + face.sleepy * 4
                opacity: 0.4 + face.concentration * 0.4
                rotation: (eye.index === 0 ? -1 : 1) * (face.concentration * 15 - face.surprise * 15)
                ShapePath {
                    fillColor: "transparent"; strokeColor: face.accent; strokeWidth: 2.7; capStyle: ShapePath.RoundCap
                    startX: 5; startY: 3
                    PathQuad { x: 23; y: 3; controlX: 14; controlY: -3 - face.smile * 2 }
                }
            }
        }
    }
    Repeater {
        model: 6
        Rectangle {
            required property int index
            x: (index < 3 ? -1 : face.width - 12) + index % 3 * 4
            y: 38; width: 2; height: 7; radius: 1; rotation: 35
            color: face.light; opacity: (0.2 + face.smile * 0.65) * (1 - face.concentration)
        }
    }
    Shape {
        x: face.width / 2; y: 36
        opacity: 1 - face.surprise
        ShapePath {
            fillColor: face.smile > 0.15 ? face.accent : "transparent"
            strokeColor: face.light; strokeWidth: 1.8; capStyle: ShapePath.RoundCap
            startX: -6 - face.smile * 2; startY: 0
            PathQuad { x: 6 + face.smile * 2; y: 0; controlX: 0; controlY: 5 - face.smile * 2 - face.concentration * 4 }
            PathQuad { x: -6 - face.smile * 2; y: 0; controlX: 0; controlY: 7 + face.smile * 12 - face.concentration * 4 }
        }
    }
    Rectangle { x: face.width / 2 - 5; y: 36; width: 10; height: 13; radius: 6; color: face.light; opacity: face.surprise }
}
