import QtQuick

Column {
    id: body
    required property QtObject theme
    required property string text
    property bool formatCode: true
    property int messageIndex: 0
    readonly property var blocks: formatCode ? chatContent.split(text) : [{kind: "text", text: text, language: ""}]
    spacing: 8
    Repeater {
        model: body.blocks
        delegate: Loader {
            id: part
            required property var modelData
            required property int index
            width: body.width
            sourceComponent: modelData.kind === "code" ? codePart : prosePart
            Component {
                id: prosePart
                TextEdit {
                    width: part.width
                    text: part.modelData.text.trim()
                    textFormat: TextEdit.PlainText
                    readOnly: true; selectByMouse: true; persistentSelection: true
                    wrapMode: TextEdit.Wrap
                    font.family: body.theme.fontFamily; font.pixelSize: 14
                    color: body.theme.ink
                    selectionColor: body.theme.accent; selectedTextColor: body.theme.accentText
                }
            }
            Component {
                id: codePart
                CodeBlock {
                    width: part.width
                    theme: body.theme; code: part.modelData.text; language: part.modelData.language
                    blockId: "chatCode" + body.messageIndex + "_" + part.index
                }
            }
        }
    }
}
