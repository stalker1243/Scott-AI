import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    required property var client
    required property QtObject theme
    required property bool darkMode
    required property bool animationsEnabled
    required property color bg
    required property color surface
    required property color elevated
    required property color ink
    required property color muted
    required property color line
    required property color accent
    property string pendingId: ""
    property string pendingText: ""
    readonly property var filtered: {
        const query = search.text.trim().toLocaleLowerCase()
        return client.memories.filter(function(item) {
            return (query.length === 0 || item.text.toLocaleLowerCase().indexOf(query) >= 0)
        })
    }
    function clearDraft() { draft.text = "" }
    function dateLabel(seconds) { return seconds > 0 ? new Date(seconds * 1000).toLocaleDateString(Qt.locale(typeof appLanguage !== "undefined" ? appLanguage.locale : "ru_RU"), Locale.ShortFormat) : "" }

    component MemoryButton: UiButton {
        theme: page.theme
        implicitHeight: 36; leftPadding: 12; rightPadding: 12
        font.pixelSize: 13
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 14
        SurfacePanel {
            objectName: "memoryDraftCard"
            theme: page.theme; flat: true
            Layout.fillWidth: true; implicitHeight: draftLayout.implicitHeight + 24
            ColumnLayout {
                id: draftLayout
                anchors.fill: parent; anchors.margins: 12; spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    UiSwitch {
                        objectName: "autoMemorySwitch"; theme: page.theme
                        text: qsTranslate("Launcher", "Запоминать автоматически")
                        checked: client.autoMemoryEnabled
                        enabled: client.online && !client.memoryBusy && client.memorySettingsAvailable
                        onToggled: client.setAutoMemoryEnabled(checked)
                    }
                    Item { Layout.fillWidth: true }
                    Text { visible: draft.text.length > 170; text: draft.text.length + " / 200"; color: draft.text.length > 200 ? page.theme.danger : page.muted; font.pixelSize: 12 }
                }
                TextField { font.family: page.theme.fontFamily;
                    id: draft; objectName: "memoryDraft"
                    Layout.fillWidth: true; implicitHeight: 40
                    enabled: !client.memoryBusy
                    color: page.ink; placeholderTextColor: page.muted
                    placeholderText: qsTranslate("Launcher", "Что запомнить?")
                    selectByMouse: true; hoverEnabled: true; leftPadding: 12; rightPadding: 12
                    selectionColor: page.accent; selectedTextColor: "white"
                    background: FieldSurface { theme: page.theme; focused: draft.activeFocus; hovered: draft.hovered; invalid: draft.text.length > 200 }
                    onAccepted: if (addButton.enabled) client.addMemory(text, "note")
                }
                RowLayout {
                    Item { Layout.fillWidth: true }
                    MemoryButton {
                        id: addButton; objectName: "addMemory"
                        text: qsTranslate("Launcher", "Запомнить"); primary: true
                        enabled: client.online && !client.memoryBusy && draft.text.trim().length > 0 && draft.text.length <= 200
                        onClicked: client.addMemory(draft.text, "note")
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            TextField { font.family: page.theme.fontFamily;
                id: search; objectName: "memorySearch"
                Layout.fillWidth: true; implicitHeight: 40; selectByMouse: true
                color: page.ink; placeholderTextColor: page.muted; placeholderText: qsTranslate("Launcher", "Найти в памяти…")
                hoverEnabled: true; leftPadding: 38; rightPadding: 38
                selectionColor: page.accent; selectedTextColor: "white"
                background: FieldSurface { theme: page.theme; fill: page.surface; focused: search.activeFocus; hovered: search.hovered }
                NavIcon { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 17; height: 17; symbol: 5; color: search.activeFocus ? page.accent : page.muted }
                MemoryButton {
                    anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                    width: 30; implicitHeight: 30; leftPadding: 0; rightPadding: 0; text: "×"
                    Accessible.name: qsTranslate("Launcher", "Очистить поиск"); visible: search.text.length > 0
                    onClicked: { search.clear(); search.forceActiveFocus() }
                }
            }
            MemoryButton { text: client.memoryBusy ? qsTranslate("Launcher", "Обновление…") : qsTranslate("Launcher", "Обновить"); enabled: client.online && !client.memoryBusy; onClicked: client.refreshMemories() }
        }
        UiNotice {
            theme: page.theme; Layout.fillWidth: true
            error: !client.online || client.memoryError.length > 0
            text: !client.online ? (client.memories.length > 0 ? qsTranslate("Launcher", "Нет подключения. Показаны последние загруженные записи.") : qsTranslate("Launcher", "Нет подключения к Scott.")) : client.memoryError.length > 0 ? client.memoryError : client.memoryNotice
        }
        SurfacePanel {
            theme: page.theme; flat: true
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 100
            Column {
                anchors.centerIn: parent; spacing: 10; visible: page.filtered.length === 0
                Text { font.family: page.theme.fontFamily; anchors.horizontalCenter: parent.horizontalCenter; text: client.memoryBusy ? qsTranslate("Launcher", "Загружаю память…") : !client.online ? qsTranslate("Launcher", "Подключите Scott") : client.memoryError.length > 0 ? qsTranslate("Launcher", "Не удалось загрузить записи") : client.memories.length === 0 ? qsTranslate("Launcher", "Здесь появится то, что важно вам") : qsTranslate("Launcher", "Ничего не найдено"); color: page.ink; font.pixelSize: 15 }
            }
            ListView {
                id: memoryList; objectName: "memoryList"
                anchors.fill: parent; anchors.margins: 16; anchors.rightMargin: 26
                clip: true; spacing: 10; model: page.filtered
                ScrollBar.vertical: UiScrollBar { theme: page.theme }
                populate: Transition { enabled: page.animationsEnabled; NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 } }
                delegate: Rectangle {
                    id: memory
                    required property var modelData
                    width: ListView.view.width; height: memoryBody.implicitHeight + 24
                    radius: 4; color: memoryHover.hovered ? page.elevated : "transparent"
                    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: page.line }
                    HoverHandler { id: memoryHover }
                    Behavior on color { enabled: page.theme.motion; ColorAnimation { duration: 160 } }
                    Behavior on border.color { enabled: page.theme.motion; ColorAnimation { duration: 160 } }
                    RowLayout {
                        id: memoryBody
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 16
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 7
                            TextEdit { font.family: page.theme.fontFamily; Layout.fillWidth: true; text: memory.modelData.text; readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; color: page.ink; font.pixelSize: 14 }
                        }
                        MemoryButton {
                            text: qsTranslate("Launcher", "Забыть"); destructive: true; enabled: client.online && !client.memoryBusy
                            onClicked: { page.pendingId = memory.modelData.id; page.pendingText = memory.modelData.text; confirmForget.open() }
                        }
                    }
                }
            }
        }
    }
    Dialog {
        id: confirmForget
        objectName: "confirmForget"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(460, parent.width - 64)
        modal: true; closePolicy: Popup.CloseOnEscape
        padding: 24
        background: SurfacePanel { theme: page.theme; color: page.theme.popup }
        contentItem: ColumnLayout {
            spacing: 18
            Text { font.family: page.theme.fontFamily; text: qsTranslate("Launcher", "Забыть эту запись?"); color: page.ink; font.pixelSize: 21; font.weight: Font.DemiBold }
            Text { font.family: page.theme.fontFamily; text: page.pendingText; color: page.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
            RowLayout {
                Layout.alignment: Qt.AlignRight; spacing: 10
                MemoryButton { text: qsTranslate("Launcher", "Отмена"); onClicked: confirmForget.close() }
                MemoryButton { text: qsTranslate("Launcher", "Забыть запись"); primary: true; destructive: true; enabled: client.online && !client.memoryBusy; onClicked: { client.forgetMemory(page.pendingId); confirmForget.close() } }
            }
        }
        enter: Transition {
            enabled: page.animationsEnabled
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160 }
                NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 220; easing.type: Easing.OutCubic }
            }
        }
        exit: Transition { enabled: page.animationsEnabled; NumberAnimation { property: "opacity"; to: 0; duration: 100 } }
    }
}
