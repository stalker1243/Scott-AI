import QtQuick
import QtQuick.Shapes

Item {
    id: robot
    required property var character
    width: 280; height: 260
    readonly property bool dark: character.variant === "black"
    readonly property color shell: dark ? "#36465e" : "#e3e9fa"
    readonly property color edge: dark ? "#101a2d" : "#7486ae"
    readonly property color light: dark ? "#607494" : "#ffffff"
    readonly property color glow: character.variant === "blue" ? "#55caff" : character.accent
    readonly property real lift: character.breath * 1.7 + character.joy * 2
    readonly property real hug: character.heart
    readonly property real pondering: character.ponder
    readonly property real glowLevel: 0.86 + character.breath * 0.1 + character.smile * 0.04

    // Move the wrist around the shoulder. A straight interpolation from a
    // lowered hand to a raised hand passes too close to the shoulder and
    // forces the elbow into a tight fold halfway through the gesture.
    function armArc(from, to, amount) {
        const start = Math.atan2(from.y, from.x)
        const end = Math.atan2(to.y, to.x)
        let turn = Math.atan2(Math.sin(end - start), Math.cos(end - start))
        const angle = start + turn * amount
        const radius = character.mix(Math.hypot(from.x, from.y), Math.hypot(to.x, to.y), amount)
        return Qt.point(Math.cos(angle) * radius, Math.sin(angle) * radius)
    }
    // Keep the elbow below/outside the shoulder during a greeting. The old
    // mirrored IK branch folded the upper arm under the helmet as it rose.
    readonly property point leftStretch: armArc(Qt.point(-20 - character.breath * 0.4, 19), Qt.point(-20, -24), character.stretch)
    readonly property point leftWork: armArc(leftStretch, Qt.point(24, 23 + Math.sin(character.actionProgress * 70)), character.work)
    readonly property point leftPose: armArc(leftWork, Qt.point(22, 14), hug)
    readonly property point rightWave: armArc(Qt.point(20 + character.breath * 0.4, 19), Qt.point(23 + Math.sin(character.greetingProgress * 18) * 2.5, -22), character.wave)
    readonly property point rightStretch: armArc(rightWave, Qt.point(20, -24), character.stretch)
    readonly property point rightWork: armArc(rightStretch, Qt.point(-24, 23 + Math.cos(character.actionProgress * 70)), character.work)
    readonly property point rightHeart: armArc(rightWork, Qt.point(-22, 14), hug)
    readonly property point rightPose: armArc(rightHeart, Qt.point(-14, -21), pondering)

    // Short knees and oversized seated boots give the silhouette a softer weight.
    PetLimb { x: 111; y: 203 - robot.lift; targetX: -11; targetY: 15 + robot.lift; upperLength: 15; lowerLength: 15; thickness: 23; bend: 1; color: robot.shell; trim: robot.edge; handWidth: 34; handHeight: 24; handColor: robot.shell; polished: true }
    PetLimb { x: 169; y: 203 - robot.lift; targetX: 11; targetY: character.held ? 22 : 15 + robot.lift; upperLength: 15; lowerLength: 17; thickness: 23; bend: -1; color: robot.shell; trim: robot.edge; handWidth: 34; handHeight: 24; handColor: robot.shell; polished: true }
    Item {
        y: -robot.lift
        Rectangle {
            x: 94; y: 147; width: 92; height: 75; radius: 28; border.width: 2; border.color: "#142034"
            gradient: Gradient { GradientStop { position: 0; color: robot.light } GradientStop { position: 0.45; color: robot.shell } GradientStop { position: 1; color: robot.edge } }
            Rectangle { x: 8; y: 9; width: 6; height: 34; radius: 3; rotation: 12; color: robot.light; opacity: 0.65 }
            Rectangle { x: 70; y: 13; width: 6; height: 36; radius: 3; rotation: -12; color: robot.edge; opacity: 0.2 }
        }
        Rectangle { x: 124; y: 142; width: 32; height: 18; radius: 8; color: "#101b2d"; border.color: "#495c7a" }
        Rectangle {
            x: 112; y: 169; width: 56; height: 40; radius: 13; color: "#0c182a"; border.width: 2; border.color: robot.edge
            Rectangle { x: 11; y: 8; width: 34; height: 9; radius: 5; color: Qt.alpha(robot.glow, 0.11) }
            Rectangle { x: 14; y: 10; width: 28; height: 4; radius: 2; color: robot.glow }
            Row { x: 13; y: 26; spacing: 7
                Repeater { model: 3; Rectangle { required property int index; width: 5; height: 5; radius: 3; color: robot.glow; opacity: character.thinking ? 0.3 + Math.abs(Math.sin(character.breath * 6 + index)) * 0.7 : 0.8 } }
            }
        }
        // The laptop unfolds before the hands reach the keys. Its screen stays
        // behind the hands so the typing remains legible at desktop scale.
        Item {
            objectName: "scottLaptop"; x: 86; y: 214; opacity: character.work; visible: opacity > 0.01
            Rectangle { x: 0; y: -5; width: 108; height: 10; radius: 4; color: "#7d96b5"; border.color: "#c1d4ea" }
            Rectangle { x: 7; y: -8; width: 94; height: 6; radius: 2; color: "#243950" }
            Rectangle {
                x: 4; y: -59; width: 100; height: 53; radius: 6; color: "#233954"; border.width: 2; border.color: "#718fba"
                transform: Rotation { origin.x: 50; origin.y: 53; axis.x: 1; axis.y: 0; axis.z: 0; angle: (1 - character.work) * 82 }
                Rectangle { anchors.fill: parent; anchors.margins: 5; radius: 3; color: "#08111e"
                    Text { x: 6; y: 12; text: "> scott.build()\n" + (character.actionProgress > 0.67 ? "✓ ready\n_" : "compiling" + ".".repeat(Math.floor(character.actionProgress * 28) % 4)); color: "#80e8bd"; font.family: "Consolas"; font.pixelSize: 7 }
                }
            }
        }
        Item {
            objectName: "scottHeart"; x: 140; y: 188; opacity: robot.hug; visible: opacity > 0.01
            scale: 0.6 + robot.hug * 0.4 + character.breath * 0.035
            Shape {
                ShapePath { fillColor: Qt.alpha(robot.glow, 0.08); strokeColor: "transparent"; PathSvg { path: "M0 -15 C-24 -40 -43 -10 -25 10 L0 33 L25 10 C43 -10 24 -40 0 -15 Z" } }
                ShapePath {
                    strokeColor: Qt.lighter(robot.glow, 1.5); strokeWidth: 2
                    fillGradient: LinearGradient { x1: -20; y1: -20; x2: 20; y2: 25; GradientStop { position: 0; color: Qt.lighter(robot.glow, 1.4) } GradientStop { position: 1; color: Qt.darker(robot.glow, 1.2) } }
                    PathSvg { path: "M0 -10 C-19 -31 -34 -8 -20 7 L0 26 L20 7 C34 -8 19 -31 0 -10 Z" }
                }
                ShapePath { strokeColor: "#e6ffff"; strokeWidth: 3; capStyle: ShapePath.RoundCap; fillColor: "transparent"; startX: -19; startY: -11; PathQuad { x: -9; y: -17; controlX: -17; controlY: -19 } }
            }
        }
        PetLimb {
            id: leftArm
            objectName: "scottLeftArm"; x: 97; y: 182; upperLength: 17; lowerLength: 18; thickness: 18; bend: -1
            targetX: robot.leftPose.x; targetY: robot.leftPose.y
            handAngle: -character.work * 10 - robot.hug * 12
            color: robot.shell; trim: robot.edge; handColor: "#1a2a43"; handWidth: 16; handHeight: 18; polished: true
        }
        PetLimb {
            id: rightArm
            objectName: "scottRightArm"; x: 183; y: 182; upperLength: 17; lowerLength: 18; thickness: 18; bend: 1
            targetX: robot.rightPose.x; targetY: robot.rightPose.y
            handAngle: character.wave * (-12 + Math.sin(character.greetingProgress * 18) * 12) + character.work * 10 + robot.hug * 12 - robot.pondering * 20
            color: robot.shell; trim: robot.edge; handColor: "#1a2a43"; handWidth: 16; handHeight: 18; polished: true
            z: 3
        }
        Repeater {
            model: 2
            Rectangle {
                required property int index
                x: (index === 0 ? 97 : 183) - width / 2; y: 182 - height / 2
                width: 16; height: 16; radius: 8; z: 4
                color: robot.shell; border.color: robot.edge; border.width: 2
                Rectangle { anchors.centerIn: parent; width: 6; height: 6; radius: 3; color: robot.edge }
            }
        }
        Item {
            parent: rightArm.grip
            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    x: -7 + index * 5; y: -14; width: 4.5; height: 8; radius: 3
                    rotation: (index - 1) * 12; color: "#293d5b"; border.color: "#7084a3"
                    opacity: character.wave; visible: opacity > 0.01
                }
            }
        }
        // A rounded, slightly tapered white helmet, with reflections painted
        // into its curves. No shader or texture is required for scaling.
        Item {
            objectName: "scottHead"; width: 280; height: 165
            rotation: character.headTilt - robot.pondering * 7 - robot.hug * 4
            transformOrigin: Item.Bottom; y: character.sleepy * 7 + character.work * 2 + Math.abs(character.nod) * 1.5
            Item {
                x: 140; y: 48; rotation: character.lookX * 6 - character.sleepy * 12
                Rectangle { x: -4; y: -22; width: 8; height: 25; radius: 4; color: robot.shell; border.color: robot.edge }
                Rectangle { x: -16; y: -44; width: 32; height: 32; radius: 16; color: Qt.alpha(robot.glow, 0.045); opacity: robot.glowLevel }
                Rectangle { x: -12; y: -40; width: 24; height: 24; radius: 12; color: "#274773"; border.color: Qt.lighter(robot.glow, 1.4); border.width: 3
                    Rectangle { anchors.centerIn: parent; width: 12; height: 12; radius: 6; color: robot.glow; border.color: "#9ceaff"; opacity: robot.glowLevel }
                }
            }
            Repeater {
                model: 2
                Item {
                    required property int index
                    x: index === 0 ? 42 : 212; y: 83; rotation: index === 0 ? 8 : -8
                    Rectangle { width: 27; height: 54; radius: 14; color: "#1c2a45"; border.color: "#0b1528"; border.width: 2 }
                    Rectangle { x: index === 0 ? -3 : 18; y: 7; width: 12; height: 40; radius: 8; color: Qt.alpha(robot.glow, 0.12) }
                    Rectangle { x: index === 0 ? 1 : 17; y: 7; width: 8; height: 40; radius: 6; color: "#386394"; border.color: robot.glow; border.width: 3 }
                    Rectangle { x: 10; y: 7; width: 6; height: 8; radius: 4; color: "#637394"; opacity: 0.4 }
                }
            }
            Shape {
                ShapePath {
                    strokeColor: "#0e182b"; strokeWidth: 3
                    fillGradient: LinearGradient { x1: 90; y1: 48; x2: 185; y2: 171
                        GradientStop { position: 0; color: robot.light }
                        GradientStop { position: 0.48; color: robot.shell }
                        GradientStop { position: 1; color: robot.dark ? "#29374e" : "#afc0e4" }
                    }
                    PathSvg { path: "M103 48 C121 44 159 44 177 48 C205 52 217 71 219 99 L219 120 C216 149 201 160 177 164 C153 168 127 168 103 164 C78 160 64 149 61 120 L61 99 C63 72 76 53 103 48 Z" }
                }
                ShapePath { strokeColor: Qt.alpha(robot.light, 0.8); strokeWidth: 2; fillColor: "transparent"
                    PathSvg { path: "M67 114 C67 76 79 57 106 53 C128 49 157 49 177 53 C198 57 209 69 213 86 M74 143 C81 155 95 158 111 160" }
                }
                ShapePath {
                    strokeColor: robot.edge; strokeWidth: 1.5
                    fillGradient: LinearGradient { x1: 100; y1: 66; x2: 174; y2: 153
                        GradientStop { position: 0; color: "#1d304b" }
                        GradientStop { position: 0.4; color: "#0a1729" }
                        GradientStop { position: 1; color: "#101d32" }
                    }
                    PathSvg { path: "M107 65 C127 62 154 62 174 66 C194 69 204 80 205 100 L204 121 C203 138 193 147 176 150 C153 153 127 153 105 150 C87 147 77 138 76 121 L76 101 C77 80 87 69 107 65 Z" }
                }
                ShapePath { strokeColor: "#070f1e"; strokeWidth: 3; fillColor: "transparent"; PathSvg { path: "M82 114 C82 83 91 73 112 70 C130 67 154 68 171 71" } }
                ShapePath { strokeColor: Qt.alpha("#718fc7", 0.16); strokeWidth: 2; fillColor: "transparent"; PathSvg { path: "M88 135 C93 143 101 145 113 146 C135 148 160 148 178 145" } }
            }
            Rectangle { x: 94; y: 55; width: 20; height: 5; radius: 4; rotation: -10; color: robot.light; opacity: 0.9 }
            Rectangle { x: 84; y: 57; width: 5; height: 4; radius: 3; color: robot.light; opacity: 0.55 }
            ScottFace { x: 94; y: 91; width: 92; accent: robot.glow; gazeX: character.lookX; gazeY: character.lookY; blink: character.blink; smile: Math.min(1, character.smile + robot.hug * 0.9); surprise: character.surprise; sleepy: character.sleepy; concentration: character.concentration; wink: Math.max(character.wink, character.wave * character.ease(0.6, 0.7, character.greetingProgress)) }
        }
    }
    Repeater {
        model: 2
        Item {
            required property int index
            x: index === 0 ? 85 : 159; y: 211; rotation: (index === 0 ? -1 : 1) * (13 + character.breath * 0.5)
            Rectangle {
                width: 39; height: 32; radius: 16; border.color: "#142035"; border.width: 2
                gradient: Gradient { GradientStop { position: 0; color: robot.light } GradientStop { position: 0.5; color: robot.shell } GradientStop { position: 1; color: robot.edge } }
                Rectangle { x: 8; y: 5; width: 27; height: 26; radius: 13; color: "#132138"; border.color: "#536b91"; border.width: 1.5
                    Rectangle { x: 7; y: 17; width: 14; height: 4; radius: 2; color: robot.glow }
                    Rectangle { x: 5; y: 3; width: 4; height: 9; radius: 3; color: "#344967"; opacity: 0.6 }
                }
            }
        }
    }
    Text { objectName: "scottQuestion"; x: 220; y: 46 + character.breath * 3; text: "?"; font.pixelSize: 32; font.bold: true; color: robot.glow; opacity: robot.pondering; rotation: 13 }
    Repeater {
        model: 3
        Text { required property int index; x: 61 - index * 12; y: 59 - index * 17 - character.breath * 3; text: "z"; font.pixelSize: 12 + index * 4; font.bold: true; color: robot.glow; opacity: character.sleepy * (0.45 + index * 0.2); rotation: -12 }
    }
}
