import QtQuick
import QtQuick.Shapes

Item {
    id: face
    property string kind: "scott"
    property color accent: "#68abff"
    property real gazeX: 0
    property real gazeY: 0
    property real blink: 1
    property real smile: 0
    property real surprise: 0
    property real sleepy: 0
    property real concentration: 0
    property real wink: 0
    readonly property bool robot: kind === "scott"
    readonly property bool samurai: kind === "russell"
    readonly property real eyeWidth: robot ? 25 : samurai ? 20 : 22
    readonly property real eyeHeight: robot ? 17 : samurai ? 21 : 25

    Repeater {
        model: 2
        Item {
            id: eye
            required property int index
            objectName: face.kind + "Eye" + index
            x: (index === 0 ? 0 : face.width - width) + face.gazeX * 2
            y: face.gazeY * 1.5
            width: face.eyeWidth; height: face.eyeHeight
            rotation: (index === 0 ? -1 : 1) * (face.smile * 6 - face.concentration * 8)
            transform: Scale {
                origin.x: eye.width / 2; origin.y: eye.height / 2
                xScale: 1 + face.surprise * 0.13
                yScale: Math.max(0.07, face.blink * (1 - face.sleepy * 0.65 - face.smile * 0.23
                       - (eye.index === 1 ? face.wink * 0.9 : 0)) + face.surprise * 0.17)
            }
            Rectangle { anchors.fill: parent; anchors.margins: -4; radius: 12; color: Qt.alpha(face.accent, 0.12); visible: face.robot }
            Rectangle {
                anchors.fill: parent; radius: width * 0.46
                color: face.robot ? face.accent : face.samurai ? "#fff4e5" : "#263143"
                Rectangle {
                    visible: face.samurai
                    x: (parent.width - width) / 2 + face.gazeX * 3; y: 3 + face.gazeY * 2
                    width: 11; height: 15; radius: 6; color: "#363342"
                    Rectangle { x: 2; y: 2; width: 4; height: 5; radius: 2; color: "white" }
                }
                Rectangle { visible: !face.samurai; x: 4 + face.gazeX * 2; y: 3 + face.gazeY; width: face.robot ? 7 : 8; height: face.robot ? 4 : 8; radius: 4; color: "#f0ffff"; opacity: 0.95 }
                Rectangle { visible: !face.samurai; x: parent.width - 7; y: parent.height - 7; width: 3; height: 3; radius: 2; color: "#f0ffff"; opacity: 0.5 }
            }
            Rectangle {
                x: 1; y: -7 - face.surprise * 4 + face.sleepy * 3; width: parent.width - 2; height: 2.5; radius: 2
                rotation: (eye.index === 0 ? -1 : 1) * (face.concentration * 15 + face.smile * 6 - face.surprise * 12)
                color: face.robot ? face.accent : face.samurai ? "#544152" : "#8c494b"
                opacity: 0.35 + face.concentration * 0.45 + face.surprise * 0.3
            }
        }
    }
    Rectangle { x: -7; y: face.eyeHeight + 2; width: 13; height: 6; radius: 4; color: face.robot ? face.accent : "#f18b99"; opacity: 0.12 + face.smile * 0.45 }
    Rectangle { x: face.width - 6; y: face.eyeHeight + 2; width: 13; height: 6; radius: 4; color: face.robot ? face.accent : "#f18b99"; opacity: 0.12 + face.smile * 0.45 }
    Shape {
        opacity: 1 - face.surprise
        ShapePath {
            fillColor: "transparent"; strokeColor: face.robot ? face.accent : face.samurai ? "#e8c98d" : "#743f46"
            strokeWidth: face.robot ? 2.5 : 3; capStyle: ShapePath.RoundCap
            startX: face.width / 2 - 8 - face.smile * 2; startY: face.eyeHeight + 10
            PathQuad { x: face.width / 2 + 8 + face.smile * 2; y: face.eyeHeight + 10; controlX: face.width / 2; controlY: face.eyeHeight + 13 + face.smile * 10 - face.concentration * 3 }
        }
    }
    Rectangle { x: face.width / 2 - width / 2; y: face.eyeHeight + 7; width: 8; height: 10; radius: 5; color: face.robot ? face.accent : "#743f46"; opacity: face.surprise }
}
