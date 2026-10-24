import QtQuick
import QtQuick.Controls
import Scott.Chat 1.0

Rectangle {
    id: block
    required property QtObject theme
    required property string code
    property string language: ""
    property string blockId: ""
    property bool copied: false
    objectName: blockId
    implicitHeight: 34 + Math.max(34, codeText.contentHeight + 24)
    radius: 8
    color: theme.elevated
    border.color: theme.line
    onCodeChanged: copied = false

    Text {
        anchors.left: parent.left; anchors.leftMargin: 12
        anchors.verticalCenter: copyButton.verticalCenter
        text: block.language || qsTranslate("Launcher", "Код")
        color: block.theme.muted
        font.family: block.theme.fontFamily; font.pixelSize: 11
        elide: Text.ElideRight
        width: Math.max(0, copyButton.x - x - 8)
    }
    UiButton {
        id: copyButton
        objectName: block.blockId + "Copy"
        theme: block.theme
        anchors.top: parent.top; anchors.topMargin: 4
        anchors.right: parent.right; anchors.rightMargin: 6
        implicitHeight: 26; leftPadding: 10; rightPadding: 10
        font.pixelSize: 11
        text: block.copied ? qsTranslate("Launcher", "Скопировано") : qsTranslate("Launcher", "Скопировать")
        onClicked: { block.copied = chatContent.copyCode(block.code); feedback.restart() }
        ToolTip.visible: hovered; ToolTip.text: qsTranslate("Launcher", "Скопировать весь блок кода")
        Accessible.name: qsTranslate("Launcher", "Скопировать код")
    }
    Timer { id: feedback; interval: 1600; onTriggered: block.copied = false }
    ScrollView {
        id: codeView
        objectName: block.blockId + "Scroll"
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: parent.top; anchors.topMargin: 34
        anchors.bottom: parent.bottom; anchors.margins: 1
        anchors.bottomMargin: 0
        clip: true
        ScrollBar.horizontal: UiScrollBar {
            theme: block.theme; parent: codeView
            x: 0; y: codeView.height - height; width: codeView.width
            active: codeView.ScrollBar.vertical.active
        }
        ScrollBar.vertical: UiScrollBar {
            theme: block.theme; parent: codeView
            x: codeView.width - width; y: 0; height: codeView.height
            active: codeView.ScrollBar.horizontal.active
        }
        contentItem: Flickable {
            id: codeScroll
            objectName: block.blockId + "Flick"
            contentWidth: Math.max(width, codeText.contentWidth + 24)
            contentHeight: codeText.contentHeight + 24
            boundsBehavior: Flickable.StopAtBounds
            TextEdit {
                id: codeText
                objectName: block.blockId + "Text"
                x: 12; y: 8
                width: Math.max(codeScroll.width - 24, contentWidth)
                height: contentHeight
                text: block.code
                textFormat: TextEdit.PlainText
                readOnly: true; selectByMouse: true; persistentSelection: true
                wrapMode: TextEdit.NoWrap
                font.family: Qt.platform.os === "windows" ? "Consolas" : "monospace"
                font.pixelSize: 13
                color: block.theme.ink
                selectionColor: block.theme.accent
                selectedTextColor: block.theme.accentText
                CodeHighlighter { source: codeText.textDocument; language: block.language; dark: block.theme.dark }
            }
        }
    }
}
