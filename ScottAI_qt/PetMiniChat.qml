import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Popup {
    id: chat
    objectName: "petMiniChat"
    required property QtObject theme
    property var controller: null
    readonly property var backend: controller ? controller.backend : null
    readonly property var browser: backend ? backend.browserState : ({})
    readonly property bool busy: controller ? controller.busy : false
    property alias draft: input.text
    popupType: Popup.Window
    width: 374
    height: 410
    implicitWidth: width
    implicitHeight: height
    contentWidth: width - leftPadding - rightPadding
    contentHeight: height - topPadding - bottomPadding
    padding: 14; margins: -1; focus: true; modal: false
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    transformOrigin: Item.Bottom
    onOpened: { if (controller) controller.open(); input.forceActiveFocus() }
    function submit() { if (controller && !busy && input.text.trim()) controller.send(input.text) }
    Connections {
        target: chat.controller
        function onSent() { input.clear(); messages.positionViewAtEnd(); if(chat.visible) Qt.callLater(function(){input.forceActiveFocus()}) }
    }
    Connections { target: chat.backend; function onMessagesChanged() { Qt.callLater(function(){ messages.positionViewAtEnd() }) } }
    background: Rectangle { color: chat.theme.popup; radius: 18; border.color: chat.theme.line }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: chat.theme.motion ? 170 : 0 }
            NumberAnimation { property: "scale"; from: 0.94; to: 1; duration: chat.theme.motion ? 210 : 0; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: chat.theme.motion ? 110 : 0 } }
    contentItem: ColumnLayout {
        spacing: 10
        RowLayout {
            Rectangle { width: 8; height: 8; radius: 4; color: chat.backend && chat.backend.online ? "#70d5aa" : chat.theme.muted }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 0
                Text { text: qsTranslate("Launcher", "Scott · мини-чат"); color: chat.theme.ink; font.pixelSize: 14; font.weight: Font.DemiBold }
                Text { text: chat.controller ? chat.controller.status : qsTranslate("Launcher", "Вопросы и команды"); color: chat.theme.muted; font.pixelSize: 11 }
            }
            ToolButton { objectName: "petChatClose"; text: "×"; implicitWidth: 28; implicitHeight: 28; Accessible.name: qsTranslate("Launcher", "Закрыть мини-чат"); onClicked: chat.close(); contentItem: Text { text: "×"; color: chat.theme.muted; font.pixelSize: 22; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter } }
        }
        ListView {
            id: messages; objectName: "petChatMessages"
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 100; clip: true; spacing: 12
            model: chat.backend ? chat.backend.messages : []
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            Text {
                visible: messages.count === 0; anchors.centerIn: parent; width: parent.width - 32
                text: qsTranslate("Launcher", "Я рядом. Что сделать?"); color: chat.theme.muted; font.pixelSize: 14; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
            }
            delegate: Column {
                required property var modelData
                width: messages.width; spacing: 4
                Text { text: parent.modelData.role === "user" ? qsTranslate("Launcher", "Вы") : "Scott"; color: parent.modelData.role === "user" ? chat.theme.muted : chat.theme.accent; font.pixelSize: 11; font.weight: Font.DemiBold }
                TextEdit {
                    width: parent.width - 8; text: parent.modelData.text; textFormat: TextEdit.PlainText
                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.WrapAtWordBoundaryOrAnywhere
                    color: chat.theme.ink; selectedTextColor: "white"; selectionColor: chat.theme.accent; font.pixelSize: 13
                }
                Repeater {
                    model: parent.modelData.attachments || []
                    Image { required property var modelData; width: messages.width - 12; height: 140; fillMode: Image.PreserveAspectFit; asynchronous: true; source: modelData.url || ""; visible: status === Image.Ready }
                }
            }
        }
        Text { Layout.fillWidth: true; visible: !!(chat.controller && chat.controller.error); text: chat.controller ? chat.controller.error.split("\n").map(function(line) { return qsTranslate("Launcher", line) }).join("\n") : ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 6; elide: Text.ElideRight; color: "#f5a69e"; font.pixelSize: 11 }
        Text { Layout.fillWidth: true; visible: !!chat.browser.message && chat.browser.state !== "idle"; text: chat.browser.message || ""; textFormat: Text.PlainText; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; color: chat.theme.muted; font.pixelSize: 11 }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: Math.max(62, Math.min(104, input.contentHeight + 24)); radius: 12
            color: "#151a21"; border.color: input.activeFocus ? chat.theme.accent : chat.theme.line
            RowLayout {
                anchors.fill: parent; anchors.margins: 10; spacing: 6
                ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    TextArea {
                        id: input; objectName: "petChatInput"; padding: 0
                        placeholderText: qsTranslate("Launcher", "Спросите или попросите…"); placeholderTextColor: chat.theme.muted
                        color: chat.theme.ink; selectionColor: chat.theme.accent; font.pixelSize: 13
                        wrapMode: TextEdit.Wrap; enabled: !chat.busy; selectByMouse: true
                        background: null
                        Accessible.name: qsTranslate("Launcher", "Сообщение мини-чата")
                        Keys.onReturnPressed: function(event) { if (!(event.modifiers & Qt.ShiftModifier)) { chat.submit(); event.accepted = true } else event.accepted = false }
                        Keys.onEnterPressed: function(event) { if (!(event.modifiers & Qt.ShiftModifier)) { chat.submit(); event.accepted = true } else event.accepted = false }
                    }
                }
                ToolButton {
                    objectName: "petChatSend"; implicitWidth: 30; implicitHeight: 32
                    enabled: !!chat.controller && (chat.backend.busy || !chat.busy && !!input.text.trim()); onClicked: chat.backend.busy ? chat.backend.cancelChatMessage() : chat.submit()
                    Accessible.name: chat.backend && chat.backend.busy ? qsTranslate("Launcher", "Остановить") : qsTranslate("Launcher", "Отправить")
                    contentItem: Text { text: chat.backend && chat.backend.busy ? "■" : chat.busy ? "…" : "↑"; color: parent.enabled ? chat.theme.accent : chat.theme.muted; font.pixelSize: 23; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
        }
    }
}
