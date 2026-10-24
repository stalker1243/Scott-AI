import QtQuick
import QtQuick.Shapes
import "PetCatalog.js" as Pets

Item {
    id: pet
    implicitWidth: 280; implicitHeight: 260
    property string kind: "scott"
    property string variant: Pets.find(kind).colors[0]
    property bool motion: true
    property bool demo: false // Legacy preview flag; large actions require an explicit event.
    property bool interactive: true
    property bool thinking: false
    property bool voiceInput: false
    property real atomPose: motion && voiceHeld && !held ? 1 : 0
    readonly property real atom: motion ? atomPose : 0
    property bool voiceHeld: false
    onVoiceInputChanged: {
        if (voiceInput) { voiceHeld = true; voiceTail.stop(); noteActivity(); performance.stop(); greeting.stop() }
        else voiceTail.restart()
    }
    Timer { id: voiceTail; interval: 500; onTriggered: { pet.voiceHeld = false; pet.tryApplicationReaction() } }
    Behavior on atomPose { NumberAnimation { duration: pet.motion ? 280 : 0; easing.type: Easing.InOutCubic } }
    property bool held: false
    property bool attention: pointer.hovered
    property real idleGazeX: 0
    property real idleGazeY: 0
    property real gazeX: pointer.hovered ? Math.max(-1, Math.min(1, (pointer.point.position.x / Math.max(1, width) - 0.5) * 2)) : idleGazeX
    property real gazeY: pointer.hovered ? Math.max(-1, Math.min(1, (pointer.point.position.y / Math.max(1, height) - 0.4) * 2)) : idleGazeY
    readonly property real lookX: motion ? lookXPose : 0
    property real lookXPose: motion ? Math.max(-1, Math.min(1, gazeX)) : 0
    readonly property real lookY: motion ? lookYPose : 0
    property real lookYPose: motion ? Math.max(-1, Math.min(1, gazeY)) : 0
    property real joy: 0
    property real breath: 0
    property real blink: 1
    property real actionProgress: 0
    property real greetingProgress: 0
    property int blinkCount: 0
    property int idleStep: 0
    property int idleSeconds: 0
    property int actionIndex: 0
    property string gesture: "wave"
    property real affection: 0
    property bool pendingApplication: false
    property real applicationDeadline: 0
    readonly property bool acting: performance.running
    readonly property color accent: Pets.color(variant)
    readonly property real flourish: acting ? Math.sin(actionProgress * Math.PI) : 0
    readonly property real work: acting ? ease(0, 0.16, actionProgress) * (1 - ease(0.83, 1, actionProgress)) : 0
    readonly property real wave: greeting.running && gesture === "wave" ? Math.sin(greetingProgress * Math.PI) : 0
    readonly property real stretch: greeting.running && gesture === "stretch" ? Math.sin(greetingProgress * Math.PI) : 0
    readonly property real heart: motion && greeting.running && gesture === "heart" ? ease(0, 0.2, greetingProgress) * (1 - ease(0.75, 1, greetingProgress)) : 0
    readonly property real wink: motion && greeting.running && gesture === "wink" ? ease(0.12, 0.28, greetingProgress) * (1 - ease(0.55, 0.72, greetingProgress)) : 0
    readonly property real nod: motion && greeting.running && gesture === "nod" ? Math.sin(greetingProgress * Math.PI * 4) * Math.sin(greetingProgress * Math.PI) : 0
    readonly property real ponder: motion ? Math.max(ponderPose, greeting.running && gesture === "think" ? Math.sin(greetingProgress * Math.PI) : 0) : 0
    property real ponderPose: motion && thinking && !acting ? 1 : 0
    readonly property real surprise: motion ? surprisePose : 0
    property real surprisePose: motion && held ? 1 : motion && kind === "spike" && acting ? ease(0.31, 0.38, actionProgress) * (1 - ease(0.45, 0.6, actionProgress)) : 0
    readonly property real sleepy: motion ? sleepyPose : 0
    property real sleepyPose: motion && !attention && !acting && !held && !thinking && !voiceHeld && idleSeconds >= 60 ? 0.8 : 0
    readonly property string emotion: !motion ? "calm" : held ? "surprised" : surprise > 0.5 ? "surprised" : joy > 0.3 || wave > 0.3 || heart > 0.3 ? "happy" : acting || thinking || ponder > 0.1 ? "focused" : sleepy > 0.3 ? "sleepy" : attention ? "curious" : "calm"
    readonly property real smile: motion ? Math.min(1, smilePose + joy * 0.85 + wave * 0.45 + wink * 0.55 + Math.abs(nod) * 0.25 + (kind === "spike" ? work * 0.55 : work * 0.12)) : 0
    property real smilePose: motion && attention ? 0.15 : 0
    readonly property real concentration: motion ? concentrationPose : 0
    property real concentrationPose: motion && (acting || thinking || ponder > 0.1) ? 0.4 : 0
    readonly property real headTilt: motion ? headTiltPose + wave * -5 + sleepy * 6 + nod * 2 : 0
    property real headTiltPose: motion ? held ? -lookX * 8 : lookX * 5 : 0
    signal interacted()
    Accessible.role: Accessible.Graphic
    Accessible.name: Pets.find(kind).name

    function ease(a, b, value) { const t = Math.max(0, Math.min(1, (value - a) / (b - a))); return t * t * (3 - 2 * t) }
    function mix(a, b, weight) { return a + (b - a) * weight }
    function noteActivity() { idleSeconds = 0; idleGazeX = 0; idleGazeY = 0 }
    function interact() {
        if (motion && !held) {
            noteActivity()
            if (!acting && !greeting.running) {
                const actions = kind === "scott" ? ["wave", "wink", "heart", "nod"] : ["wave", "popcorn", "heart", "nod"]
                if (playAction(actions[actionIndex % actions.length])) actionIndex++
            }
            reaction.restart()
        }
        interacted()
    }
    function playAction(action) {
        if (!motion || held || voiceHeld || acting || greeting.running) return false
        if (action === "laptop" || action === "popcorn") { noteActivity(); performance.start(); return true }
        if (["wave", "stretch", "think", "heart", "wink", "nod"].indexOf(action) < 0) return false
        noteActivity()
        gesture = action; greeting.restart(); return true
    }
    function applicationOpened() {
        if (!motion) return
        noteActivity()
        if (kind !== "scott") { reaction.restart(); return }
        if (acting) return // Coalesce a burst of launches into one terminal action.
        pendingApplication = true; applicationDeadline = Date.now() + 10000
        tryApplicationReaction()
    }
    function tryApplicationReaction() {
        if (!pendingApplication) return
        if (!motion || Date.now() > applicationDeadline) { pendingApplication = false; return }
        if (held || voiceHeld || acting || greeting.running) return
        pendingApplication = false; playAction("laptop")
    }
    function replyArrived() {
        noteActivity()
        if (motion && !held) reaction.restart()
        tryApplicationReaction()
    }
    function petHead() {
        if (!motion || held) return
        noteActivity()
        if (voiceHeld) { reaction.restart(); return }
        reaction.restart(); affectionAnimation.restart()
        if (!acting) { gesture = kind === "scott" ? "heart" : "wave"; greeting.restart() }
    }
    function stopMotion() {
        performance.stop(); greeting.stop(); eyelids.stop(); reaction.stop(); affectionAnimation.stop(); affection = 0
        blink = 1; joy = 0; breath = 0; idleStep = 0; pendingApplication = false; noteActivity()
        // Rendered values also use motion explicitly: a disabled Behavior may
        // still have an interpolation in flight when reduced motion is selected.
        for (const transition of [lookEaseX, lookEaseY, smileEase, focusEase, surpriseEase, sleepyEase, ponderEase, headEase, bodyEaseY, bodyEaseRotation]) transition.complete()
    }
    // Retired companions fall back to Scott. Keep Spike's artwork below for
    // a later return; it cannot be selected or rendered in this version.
    onKindChanged: { if (kind !== "scott") { kind = "scott"; return } performance.stop(); greeting.stop(); reaction.stop(); affectionAnimation.stop(); affection = 0; actionIndex = 0; actionProgress = 0; joy = 0; pendingApplication = false; noteActivity() }
    onAttentionChanged: if (attention) noteActivity()
    onThinkingChanged: { if (thinking) noteActivity(); else tryApplicationReaction() }
    onHeldChanged: { noteActivity(); if (held) { performance.stop(); greeting.stop() } else if (motion) { reaction.restart(); tryApplicationReaction() } }
    onMotionChanged: if (!motion) stopMotion()
    Behavior on lookXPose { enabled: pet.motion; NumberAnimation { id: lookEaseX; duration: 160; easing.type: Easing.OutCubic } }
    Behavior on lookYPose { enabled: pet.motion; NumberAnimation { id: lookEaseY; duration: 160; easing.type: Easing.OutCubic } }
    Behavior on smilePose { enabled: pet.motion; NumberAnimation { id: smileEase; duration: 180; easing.type: Easing.OutCubic } }
    Behavior on concentrationPose { enabled: pet.motion; NumberAnimation { id: focusEase; duration: 240 } }
    Behavior on surprisePose { enabled: pet.motion; NumberAnimation { id: surpriseEase; duration: 140; easing.type: Easing.OutCubic } }
    Behavior on sleepyPose { enabled: pet.motion; NumberAnimation { id: sleepyEase; duration: 550; easing.type: Easing.InOutSine } }
    Behavior on ponderPose { enabled: pet.motion; NumberAnimation { id: ponderEase; duration: 260; easing.type: Easing.InOutSine } }
    Behavior on headTiltPose { enabled: pet.motion; NumberAnimation { id: headEase; duration: 380; easing.type: Easing.OutCubic } }
    SequentialAnimation {
        id: reaction
        NumberAnimation { target: pet; property: "joy"; to: 1; duration: 180; easing.type: Easing.OutBack }
        PauseAnimation { duration: 200 }
        NumberAnimation { target: pet; property: "joy"; to: 0; duration: 1100; easing.type: Easing.InOutSine }
    }
    NumberAnimation { id: affectionAnimation; target: pet; property: "affection"; from: 0; to: 1; duration: 1400; onStopped: pet.affection = 0 }
    SequentialAnimation on breath {
        running: pet.motion && pet.visible; loops: Animation.Infinite
        NumberAnimation { to: 1; duration: 1900; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: 1900; easing.type: Easing.InOutSine }
    }
    SequentialAnimation {
        id: eyelids; loops: pet.blinkCount % 3 === 0 ? 2 : 1
        NumberAnimation { target: pet; property: "blink"; to: 0.07; duration: 90; easing.type: Easing.InQuad }
        NumberAnimation { target: pet; property: "blink"; to: 1; duration: 180; easing.type: Easing.OutCubic }
        PauseAnimation { duration: 140 }
    }
    Timer { interval: 3900; repeat: true; running: pet.motion && pet.visible; onTriggered: { pet.blinkCount++; eyelids.restart() } }
    Timer {
        objectName: "petIdleClock"; interval: 1000; repeat: true; running: pet.motion && pet.visible
        onTriggered: {
            if (pet.attention || pet.held || pet.acting || greeting.running || pet.thinking) { pet.idleSeconds = 0; return }
            pet.idleSeconds++
            if (pet.idleSeconds % 7 !== 0) return
            pet.idleStep++
            const looks = [[0, 0], [-0.35, 0.1], [0.4, -0.15], [0, 0.2], [-0.15, 0.25]]
            pet.idleGazeX = looks[pet.idleStep % 5][0]; pet.idleGazeY = looks[pet.idleStep % 5][1]
        }
    }
    NumberAnimation { id: greeting; objectName: "petGreeting"; target: pet; property: "greetingProgress"; from: 0; to: 1; duration: pet.gesture === "heart" ? 3400 : pet.gesture === "think" ? 3800 : pet.gesture === "wink" ? 1700 : pet.gesture === "nod" ? 1900 : 2400; onStopped: { pet.greetingProgress = 0; Qt.callLater(pet.tryApplicationReaction) } }
    NumberAnimation { id: performance; objectName: "petPerformance"; target: pet; property: "actionProgress"; from: 0; to: 1; duration: 6800; onStopped: { pet.actionProgress = 0; Qt.callLater(pet.tryApplicationReaction) } }
    TapHandler { enabled: pet.interactive; acceptedButtons: Qt.LeftButton; onTapped: pet.interact() }
    HoverHandler { id: pointer; enabled: pet.interactive; cursorShape: Qt.PointingHandCursor }

    Item {
        width: 280; height: 260; anchors.centerIn: parent
        scale: Math.min(pet.width / 280, pet.height / 260)
        Rectangle { x: 76; y: 226; width: 128; height: 11; radius: 50; color: Qt.alpha(pet.accent, 0.14); scale: pet.held ? 0.72 : 1 - pet.joy * 0.08 }
        Item {
            id: body
            width: 280; height: 260
            property real offsetY: pet.held ? -8 : -pet.joy * 3 - pet.stretch * 3
            y: pet.motion ? offsetY : 0
            property real lean: pet.held ? -pet.lookX * 4 : pet.lookX * 1.2
            rotation: pet.motion ? lean : 0
            transformOrigin: Item.Bottom
            Behavior on offsetY { enabled: pet.motion; NumberAnimation { id: bodyEaseY; duration: 220; easing.type: Easing.OutCubic } }
            Behavior on lean { enabled: pet.motion; NumberAnimation { id: bodyEaseRotation; duration: 180 } }

            ScottRobot { visible: pet.kind === "scott"; character: pet }

            Item {
                id: spike; visible: pet.kind === "spike"
                readonly property bool icy: pet.variant === "cyan"
                readonly property color edge: icy ? "#8df4ff" : "#ffb26b"
                readonly property color limbColor: icy ? "#339ccf" : "#f7814a"
                readonly property real hop: pet.joy * 4 + pet.surprise * 4
                PetLimb { x: 111; y: 205 - spike.hop; targetX: -5; targetY: 15 + spike.hop; upperLength: 12; lowerLength: 12; thickness: 14; bend: 1; color: spike.limbColor; trim: spike.edge; handColor: spike.limbColor; handWidth: 31; handHeight: 14; jointVisible: false }
                PetLimb { x: 169; y: 205 - spike.hop; targetX: 5; targetY: pet.held ? 22 : 15 + spike.hop; upperLength: 12; lowerLength: 12; thickness: 14; bend: -1; color: spike.limbColor; trim: spike.edge; handColor: spike.limbColor; handWidth: 31; handHeight: 14; jointVisible: false }
                Item {
                    y: -spike.hop
                    transform: Scale { origin.x: 140; origin.y: 220; xScale: 1 + pet.breath * 0.018 - pet.surprise * 0.03 - pet.stretch * 0.04; yScale: 1 - pet.breath * 0.018 + pet.surprise * 0.04 + pet.stretch * 0.04 }
                    Shape {
                        ShapePath {
                            strokeColor: spike.edge; strokeWidth: 2
                            fillGradient: LinearGradient { x1: 140; y1: 45; x2: 140; y2: 220
                                GradientStop { position: 0; color: spike.icy ? "#99f4ff" : "#ffe7a1" }
                                GradientStop { position: 0.5; color: spike.icy ? "#2ea9e2" : "#ff975c" }
                                GradientStop { position: 1; color: spike.icy ? "#3267bf" : "#e5574a" }
                            }
                            startX: 142; startY: 35
                            PathCubic { x: 178; y: 98; control1X: 167 + pet.lookX * 4; control1Y: 76; control2X: 143; control2Y: 78 }
                            PathCubic { x: 191; y: 65; control1X: 193; control1Y: 81; control2X: 184; control2Y: 77 }
                            PathCubic { x: 218; y: 142; control1X: 210; control1Y: 99; control2X: 204; control2Y: 110 }
                            PathCubic { x: 144; y: 221; control1X: 241; control1Y: 196; control2X: 202; control2Y: 223 }
                            PathCubic { x: 64; y: 157; control1X: 86; control1Y: 224; control2X: 47; control2Y: 201 }
                            PathCubic { x: 80; y: 117; control1X: 71; control1Y: 140; control2X: 76; control2Y: 133 }
                            PathCubic { x: 92; y: 141; control1X: 92; control1Y: 130; control2X: 90; control2Y: 138 }
                            PathCubic { x: 111; y: 86; control1X: 112; control1Y: 119; control2X: 100; control2Y: 109 }
                            PathCubic { x: 142; y: 35; control1X: 129; control1Y: 106; control2X: 139 + pet.breath * 6; control2Y: 80 }
                        }
                        ShapePath { fillColor: spike.icy ? "#abf9ff" : "#ffd492"; strokeColor: "transparent"; PathSvg { path: "M139 128 C157 150 145 151 168 165 C185 180 181 205 144 212 C108 208 103 187 114 170 C118 188 138 168 139 128 Z" } }
                    }
                    PetFace { x: 101 + pet.lookX * 2; y: 135 + pet.lookY * 2; width: 78; kind: "spike"; gazeX: pet.lookX; gazeY: pet.lookY; blink: pet.blink; smile: pet.smile; surprise: pet.surprise; sleepy: pet.sleepy; concentration: pet.concentration; wink: pet.wink; rotation: pet.headTilt * 0.4 }
                    Item {
                        x: 108; y: 200; width: 64; height: 40; opacity: pet.work; visible: opacity > 0.01
                        Shape { ShapePath { fillColor: "#f9eada"; strokeColor: "#ffffff"; strokeWidth: 1; PathSvg { path: "M0 0 L64 0 L55 36 L9 36 Z" } } }
                        Row { x: 13; y: 4; spacing: 10; Repeater { model: 3; Rectangle { width: 6; height: 28; radius: 2; color: spike.icy ? "#3399cb" : "#e85c57" } } }
                        Text { x: 19; y: 10; text: "POP"; color: "#673b39"; font.pixelSize: 10; font.bold: true; rotation: -5 }
                        Repeater {
                            model: 12
                            Item {
                                required property int index
                                readonly property real flight: Math.max(0, Math.min(1, (pet.actionProgress - 0.33 - index * 0.012) * 3))
                                x: 5 + index * 17 % 47; y: -6 - Math.sin(flight * Math.PI) * (16 + index % 3 * 8)
                                visible: pet.actionProgress > 0.33 + index * 0.012
                                rotation: Math.sin(index * 1.7) * flight * 100
                                Rectangle { width: 11; height: 9; radius: 5; color: "#fff3d4"; border.color: "#e7ca98" }
                                Rectangle { x: 4; y: -3; width: 8; height: 8; radius: 4; color: "#fff8e5" }
                            }
                        }
                    }
                    PetLimb {
                        id: cornArm; objectName: "spikeLeftArm"; x: 78; y: 165; upperLength: 29; lowerLength: 26; thickness: 15; bend: 1
                        targetX: pet.mix(pet.mix(-8, -18, pet.stretch), 33, pet.work); targetY: pet.mix(pet.mix(27, -29, pet.stretch), 33 - pet.ease(0.18, 0.32, pet.actionProgress) * 18, pet.work)
                        handAngle: -pet.work * 10; color: spike.limbColor; trim: spike.edge; handColor: spike.icy ? "#7fe5f5" : "#ffbe75"; jointVisible: false
                    }
                    PetLimb {
                        objectName: "spikeRightArm"; x: 202; y: 165; upperLength: 29; lowerLength: 26; thickness: 15; bend: -1
                        targetX: pet.mix(pet.mix(pet.mix(8, 24, pet.wave), 18, pet.stretch), -31, pet.work); targetY: pet.mix(pet.mix(pet.mix(27, -16, pet.wave), -29, pet.stretch), 38, pet.work)
                        handAngle: pet.wave * Math.sin(pet.greetingProgress * 22) * 25; color: spike.limbColor; trim: spike.edge; handColor: spike.icy ? "#7fe5f5" : "#ffbe75"; jointVisible: false
                    }
                    Item {
                        objectName: "spikeCorn"; parent: cornArm.grip
                        opacity: pet.work * (1 - pet.ease(0.3, 0.39, pet.actionProgress)); visible: opacity > 0.01
                        Rectangle { x: -9; y: -28; width: 18; height: 30; radius: 9; color: "#ffd363"; border.color: "#ffeb9d"
                            Grid { anchors.centerIn: parent; columns: 3; spacing: 2; Repeater { model: 12; Rectangle { width: 3; height: 3; radius: 2; color: "#fff1a4" } } }
                        }
                        Rectangle { x: -8; y: -1; width: 16; height: 12; radius: 5; color: "#8cbb69" }
                    }
                }
            }
        }
        Repeater {
            model: 3
            Item {
                required property int index
                x: 89 + index * 43; y: 72 - pet.affection * 32 + (index % 2) * 13
                opacity: pet.motion && pet.affection > 0 ? Math.sin(pet.affection * Math.PI) * 0.8 : 0
                scale: 0.7 + pet.affection * 0.4
                Shape { ShapePath { fillColor: Qt.alpha(pet.accent, 0.9); strokeColor: "transparent"; PathSvg { path: "M0 5 C-7 -2 -12 5 -8 10 L0 17 L8 10 C12 5 7 -2 0 5 Z" } } }
            }
        }
    }
}
