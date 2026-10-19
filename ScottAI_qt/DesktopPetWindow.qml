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
    property bool doubleClickRelease: false
    PetCharacter {
        id: character; objectName: "desktopPetCharacter"; anchors.fill: parent
        kind: petService.kind; variant: petService.variant; motion: petService.motion
        interactive: false; held: petService.dragging; attention: pointer.containsMouse
        thinking: !!chatController && chatController.busy
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
            if (mouse.button === Qt.RightButton) actions.popup(Qt.point(mouse.x, mouse.y))
        }
        onWheel: function(wheel) {
            if (wheel.modifiers & Qt.ControlModifier) petService.setSizePercent(petService.sizePercent + (wheel.angleDelta.y > 0 ? 10 : -10))
            else wheel.accepted = false
        }
    }
    Timer { id: singleClick; objectName: "petSingleClick"; interval: Qt.styleHints.mouseDoubleClickInterval; onTriggered: character.interact() }
    Connections { target: petService; function onPlay() { character.interact() } function onApplicationOpened() { character.applicationOpened() } function onDragChanged() { if(petService.dragging) { singleClick.stop(); miniChat.close() } } }
    Connections { target: chatController; function onSent() { character.replyArrived() } }
    Timer { id: openChat; interval: 120; onTriggered: { const point = petService.chatPosition(miniChat.width, miniChat.height); miniChat.x = point.x; miniChat.y = point.y; miniChat.open() } }
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
        onAboutToShow: petService.menuOpen(true)
        onClosed: petService.menuOpen(false)
        UiMenuItem { objectName: "petHide"; theme: menuTheme; text: qsTranslate("Launcher", "Скрыть питомца"); onTriggered: petService.stop() }
        UiMenuItem { objectName: "petOpenChat"; theme: menuTheme; text: qsTranslate("Launcher", "Написать в мини-чат"); onTriggered: openChat.restart() }
    }
}
