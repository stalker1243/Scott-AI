import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "PetCatalog.js" as Pets

Window {
    id: petWindow
    objectName: "desktopPetWindow"
    width: 280; height: 260
    visible: true; color: "transparent"
    title: Pets.find(petService.kind).name + qsTranslate("Launcher", " · питомец Scott AI")
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
    Component.onCompleted: petService.attach(petWindow)
    onClosing: petService.stop()
    property var chatController: typeof petChat !== "undefined" ? petChat : null
    readonly property var voiceClient: chatController ? chatController.backend : null
    readonly property bool voiceActive: !!voiceClient && voiceClient.online && voiceClient.listeningReady && voiceClient.listening
    function watchInput() { if (voiceClient) voiceClient.inputMonitoring = visible && voiceActive }
    onVoiceActiveChanged: watchInput()
    onVisibleChanged: watchInput()
    property bool doubleClickRelease: false
    property bool chatRequested: false
    function openRequestedChat() {
        if (!chatRequested || actions.visible) return
        chatRequested = false
        const point = petService.chatPosition(miniChat.width, miniChat.height)
        miniChat.x = point.x; miniChat.y = point.y
        miniChat.open()
    }
    function requestMiniChat() {
        chatRequested = true
        if (actions.visible) actions.close()
        else Qt.callLater(openRequestedChat)
    }
    PetCharacter {
        id: character; objectName: "desktopPetCharacter"; anchors.fill: parent
        kind: petService.kind; variant: petService.variant; motion: petService.motion
        interactive: false; held: petService.dragging; attention: pointer.containsMouse
        thinking: !!chatController && chatController.busy
        voiceInput: petWindow.voiceActive && (petWindow.voiceClient.inputLevel || 0) > 0.015
        gazeX: petService.canReposition || pointer.containsMouse ? petService.gazeX : idleGazeX
        gazeY: petService.canReposition || pointer.containsMouse ? petService.gazeY : idleGazeY
    }
    MouseArea {
        id: pointer; objectName: "petPointerArea"; anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton; hoverEnabled: true; preventStealing: true
        cursorShape: petService.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        onPressed: function(mouse) { if (mouse.button === Qt.LeftButton) { petWindow.doubleClickRelease = false; petService.beginDrag(Qt.point(mouse.x, mouse.y)) } }
        onPositionChanged: function(mouse) { petService.updateDrag(Qt.point(mouse.x, mouse.y)) }
        onReleased: function(mouse) {
            if (mouse.button !== Qt.LeftButton) return
            const dragged = petService.endDrag()
            if (!dragged && !petWindow.doubleClickRelease) singleClick.restart()
            petWindow.doubleClickRelease = false
        }
        onDoubleClicked: function(mouse) { if (mouse.button === Qt.LeftButton) { singleClick.stop(); petWindow.doubleClickRelease = true; character.petHead() } }
        onCanceled: { singleClick.stop(); petService.endDrag() }
        onClicked: function(mouse) {
            if (mouse.button === Qt.RightButton) {
                singleClick.stop()
                petWindow.chatRequested = false
                miniChat.close()
                actions.popup(petService.chatPosition(actions.width, actions.height))
            }
        }
        onWheel: function(wheel) {
            if (wheel.modifiers & Qt.ControlModifier) petService.setSizePercent(petService.sizePercent + (wheel.angleDelta.y > 0 ? 10 : -10))
            else wheel.accepted = false
        }
    }
    Timer { id: singleClick; objectName: "petSingleClick"; interval: Qt.styleHints.mouseDoubleClickInterval; onTriggered: character.interact() }
    Connections { target: petService; function onPlay() { character.interact() } function onApplicationOpened() { character.applicationOpened() } function onDragChanged() { if(petService.dragging) { singleClick.stop(); petWindow.chatRequested = false; miniChat.close() } } }
    Connections { target: chatController
        function onSent() { character.replyArrived() }
        function onChanged() { petWindow.watchInput() }
        function onVoiceFailed() { petWindow.requestMiniChat() }
    }
    PetMiniChat { id: miniChat; theme: menuTheme; controller: petWindow.chatController; width: Math.min(374, petWindow.Screen.width - 24); height: Math.min(410, petWindow.Screen.height - 48) }
    QtObject {
        id: menuTheme
        property color popup: "#202329"
        property color line: "#343941"
        property color ink: "#e9edf2"
        property color muted: "#a0a7b2"
        property color accent: character.accent
        property int controlRadius: 8
        property string fontFamily: "Segoe UI"
        property bool motion: petService.motion
    }
    UiMenu {
        id: actions; objectName: "petContextMenu"; theme: menuTheme; popupType: Popup.Window
        implicitWidth: 144; implicitHeight: 56
        contentItem: ListView {
            implicitWidth: 132; implicitHeight: 44
            orientation: ListView.Horizontal; model: actions.contentModel
            interactive: false; spacing: 0
        }
        onAboutToShow: petService.menuOpen(true)
        onClosed: { petService.menuOpen(false); Qt.callLater(petWindow.openRequestedChat) }
        component PetAction: UiMenuItem {
            required property int symbol
            theme: menuTheme; width: 44; height: 44
            implicitWidth: 44; implicitHeight: 44
            Accessible.name: text
            ToolTip.visible: hovered || visualFocus; ToolTip.text: text; ToolTip.delay: 250
            contentItem: NavIcon { symbol: parent.symbol; color: parent.highlighted || (parent.symbol === 13 && petWindow.voiceActive) ? menuTheme.accent : menuTheme.ink; opacity: parent.enabled ? 1 : 0.4; width: 22; height: 22 }
        }
        PetAction { objectName: "petHide"; symbol: 14; text: qsTranslate("Launcher", "Скрыть питомца"); onTriggered: { petWindow.chatRequested = false; petService.stop() } }
        PetAction { objectName: "petOpenChat"; symbol: 1; text: qsTranslate("Launcher", "Написать в мини-чат"); onTriggered: petWindow.requestMiniChat() }
        PetAction {
            objectName: "petVoice"; symbol: 13
            text: petWindow.voiceActive ? qsTranslate("Launcher", "Остановить микрофон") : qsTranslate("Launcher", "Запустить Скотта")
            enabled: !!petWindow.chatController && (!petWindow.voiceClient || !petWindow.voiceClient.listeningBusy)
            onTriggered: petWindow.chatController.toggleVoice()
        }
    }
}
