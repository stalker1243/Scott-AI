import QtQuick

// Two connected bones. The hand target is clamped to the reachable circle;
// the elbow is solved from the triangle, so neither joint can come apart.
Item {
    id: limb
    property real targetX: 0
    property real targetY: 48
    property real upperLength: 27
    property real lowerLength: 25
    property real thickness: 17
    property real bend: 1
    property real handAngle: 0
    property color color: "#263b57"
    property color trim: "#4d6d90"
    property color handColor: "#91abc2"
    property real handWidth: thickness * 1.05
    property real handHeight: thickness
    property bool jointVisible: true
    property bool polished: false
    property alias grip: hand
    readonly property real distance: Math.max(Math.abs(upperLength - lowerLength) + 0.1,
                                              Math.min(upperLength + lowerLength - 0.1, Math.hypot(targetX, targetY)))
    readonly property real direction: Math.atan2(targetY, targetX)
    readonly property real shoulderAngle: (direction + bend * Math.acos(Math.max(-1, Math.min(1,
        (upperLength * upperLength + distance * distance - lowerLength * lowerLength) / (2 * upperLength * distance))))) * 180 / Math.PI
    readonly property real elbowX: upperLength * Math.cos(shoulderAngle * Math.PI / 180)
    readonly property real elbowY: upperLength * Math.sin(shoulderAngle * Math.PI / 180)
    readonly property real handX: Math.cos(direction) * distance
    readonly property real handY: Math.sin(direction) * distance
    readonly property real forearmAngle: Math.atan2(handY - elbowY, handX - elbowX) * 180 / Math.PI

    Item {
        rotation: limb.shoulderAngle
        Rectangle {
            y: -height / 2; width: limb.upperLength + 2; height: limb.thickness; radius: height / 2; color: limb.color; border.color: limb.trim
            gradient: Gradient {
                GradientStop { position: 0; color: limb.polished ? Qt.lighter(limb.color, 1.13) : limb.color }
                GradientStop { position: 0.45; color: limb.color }
                GradientStop { position: 1; color: limb.polished ? Qt.darker(limb.color, 1.22) : limb.color }
            }
            Rectangle { visible: limb.polished; x: 7; y: 3; width: parent.width * 0.48; height: 3; radius: 2; color: "#ffffff"; opacity: 0.7 }
        }
        Item {
            x: limb.upperLength; rotation: limb.forearmAngle - limb.shoulderAngle
            Rectangle {
                y: -height / 2; width: limb.lowerLength; height: limb.thickness * 0.84; radius: height / 2; color: limb.color; border.color: limb.trim
                gradient: Gradient {
                    GradientStop { position: 0; color: limb.polished ? Qt.lighter(limb.color, 1.12) : limb.color }
                    GradientStop { position: 0.55; color: limb.color }
                    GradientStop { position: 1; color: limb.polished ? Qt.darker(limb.color, 1.2) : limb.color }
                }
                Rectangle { visible: limb.polished; x: parent.width - 8; y: 2; width: 3; height: parent.height - 4; radius: 1; color: limb.trim; opacity: 0.45 }
            }
        }
    }
    Rectangle { x: limb.elbowX - width / 2; y: limb.elbowY - height / 2; width: limb.thickness * 0.64; height: width; radius: width / 2; visible: limb.jointVisible; color: limb.trim; border.color: Qt.lighter(limb.trim, 1.25) }
    Item {
        id: hand
        x: limb.handX; y: limb.handY; rotation: limb.handAngle
        Rectangle {
            x: -width / 2; y: -height / 2; width: limb.handWidth; height: limb.handHeight; radius: height * 0.43; color: limb.handColor; border.color: limb.trim
            gradient: Gradient {
                GradientStop { position: 0; color: limb.polished ? Qt.lighter(limb.handColor, 1.4) : limb.handColor }
                GradientStop { position: 1; color: limb.handColor }
            }
            Rectangle { visible: limb.polished; x: 4; y: 3; width: parent.width * 0.45; height: 2; radius: 1; color: "#a6bedc"; opacity: 0.35 }
        }
    }
}
