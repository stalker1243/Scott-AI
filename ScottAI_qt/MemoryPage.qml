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
    property string activeKind: ""
    property string pendingId: ""
    property string pendingText: ""
    readonly property var filtered: {
        const query = search.text.trim().toLocaleLowerCase()
        return client.memories.filter(function(item) {
            return (activeKind.length === 0 || item.kind === activeKind)
                && (query.length === 0 || item.text.toLocaleLowerCase().indexOf(query) >= 0)
        })
    }
    function clearDraft() { draft.text = "" }
    function categoryName(key) {
        for (let i = 0; i < client.memoryKinds.length; ++i)
            if (client.memoryKinds[i].id === key) return client.memoryKinds[i].title
        return key
    }
    function dateLabel(seconds) { return seconds > 0 ? Qt.formatDate(new Date(seconds * 1000), "dd.MM.yyyy") : "" }

    component MemoryButton: UiButton {
        theme: page.theme
        implicitHeight: 40; leftPadding: 16; rightPadding: 16
        font.pixelSize: 13
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 14
        SurfacePanel {
            objectName: "memoryDraftCard"
            theme: page.theme
            Layout.fillWidth: true; implicitHeight: draftLayout.implicitHeight + 32; radius: page.theme.cardRadius; color: page.surface; border.color: page.line
            ColumnLayout {
                id: draftLayout
                anchors.fill: parent; anchors.margins: 16; spacing: 8
                RowLayout {
                    Text { font.family: page.theme.fontFamily; text: "Новая запись"; color: page.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                    Item { Layout.fillWidth: true }
                    UiSwitch {
                        objectName: "autoMemorySwitch"
                        theme: page.theme; text: "Запоминать факты"
                        ToolTip.visible: hovered
                        ToolTip.text: "Сохранять явно сказанные сведения о вас и проектах. История разговоров хранится отдельно."
                        checked: client.autoMemoryEnabled
                        enabled: client.online && !client.memoryBusy && client.memorySettingsAvailable
                        onToggled: client.setAutoMemoryEnabled(checked)
                    }
                    Text { font.family: page.theme.fontFamily; text: draft.text.length + " / 200"; color: draft.text.length > 200 ? "#d87e68" : page.muted; font.pixelSize: 12 }
                }
                TextField { font.family: page.theme.fontFamily;
                    id: draft; objectName: "memoryDraft"
                    Layout.fillWidth: true; implicitHeight: 40
                    enabled: !client.memoryBusy
                    color: page.ink; placeholderTextColor: page.muted
                    placeholderText: "Что запомнить?"
                    selectByMouse: true; hoverEnabled: true; leftPadding: 12; rightPadding: 12
                    selectionColor: page.accent; selectedTextColor: "white"
                    background: FieldSurface { theme: page.theme; focused: draft.activeFocus; hovered: draft.hovered; invalid: draft.text.length > 200 }
                    onAccepted: if (addButton.enabled) client.addMemory(text, kindBox.currentValue)
                }
                RowLayout {
                    ComboBox { font.family: page.theme.fontFamily;
                        id: kindBox; objectName: "memoryKind"
                        Layout.preferredWidth: 180; implicitHeight: 40
                        model: client.memoryKinds; textRole: "title"; valueRole: "id"
                        enabled: !client.memoryBusy && count > 0
                        palette.text: page.ink; palette.buttonText: page.ink; palette.window: page.surface
                        palette.base: page.surface; palette.highlight: page.accent; palette.highlightedText: "white"
                        contentItem: Text { font.family: page.theme.fontFamily; text: kindBox.displayText; leftPadding: 12; rightPadding: 24; color: page.ink; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                        hoverEnabled: true
                        background: FieldSurface { theme: page.theme; focused: kindBox.activeFocus || kindBox.popup.visible; hovered: kindBox.hovered }
                        indicator: NavIcon {
                            x: kindBox.width - width - 12; y: (kindBox.height - height) / 2
                            width: 16; height: 16; symbol: 6; color: page.muted
                            rotation: kindBox.popup.visible ? 180 : 0
                            Behavior on rotation { enabled: page.theme.motion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        }
                        delegate: ItemDelegate {
                            required property int index
                            required property var modelData
                            width: kindBox.width - 8; height: 38
                            text: modelData.title
                            highlighted: kindBox.highlightedIndex === index
                            contentItem: Text { font.family: page.theme.fontFamily; text: modelData.title; color: highlighted ? page.accent : page.ink; verticalAlignment: Text.AlignVCenter; leftPadding: 8 }
                            background: Rectangle { radius: page.theme.controlRadius; color: highlighted ? page.elevated : "transparent" }
                        }
                        popup: Popup {
                            objectName: "memoryKindPopup"
                            y: kindBox.height + 6; width: kindBox.width; padding: 4
                            implicitHeight: contentItem.implicitHeight + 8
                            background: Rectangle { radius: page.theme.controlRadius; color: page.theme.popup; border.color: page.line }
                            contentItem: ListView {
                                implicitHeight: contentHeight; clip: true
                                model: kindBox.popup.visible ? kindBox.delegateModel : null
                                currentIndex: kindBox.highlightedIndex
                                ScrollIndicator.vertical: ScrollIndicator {}
                            }
                            enter: Transition { enabled: page.theme.motion; NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 130 } }
                            exit: Transition { enabled: page.theme.motion; NumberAnimation { property: "opacity"; to: 0; duration: 90 } }
                        }
                    }
                    Item { Layout.fillWidth: true }
                    MemoryButton {
                        id: addButton; objectName: "addMemory"
                        text: "Запомнить"; primary: true
                        enabled: client.online && !client.memoryBusy && draft.text.trim().length > 0 && draft.text.length <= 200 && kindBox.currentIndex >= 0
                        onClicked: client.addMemory(draft.text, kindBox.currentValue)
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            TextField { font.family: page.theme.fontFamily;
                id: search; objectName: "memorySearch"
                Layout.fillWidth: true; implicitHeight: 40; selectByMouse: true
                color: page.ink; placeholderTextColor: page.muted; placeholderText: "Найти в памяти…"
                hoverEnabled: true; leftPadding: 38; rightPadding: 38
                selectionColor: page.accent; selectedTextColor: "white"
                background: FieldSurface { theme: page.theme; fill: page.surface; focused: search.activeFocus; hovered: search.hovered }
                NavIcon { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 17; height: 17; symbol: 5; color: search.activeFocus ? page.accent : page.muted }
                MemoryButton {
                    anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                    width: 30; implicitHeight: 30; leftPadding: 0; rightPadding: 0; text: "×"
                    Accessible.name: "Очистить поиск"; visible: search.text.length > 0
                    onClicked: { search.clear(); search.forceActiveFocus() }
                }
            }
            MemoryButton { text: client.memoryBusy ? "Обновление…" : "Обновить"; enabled: client.online && !client.memoryBusy; onClicked: client.refreshMemories() }
        }
        Flow {
            Layout.fillWidth: true; spacing: 8
            Repeater {
                model: [{id: "", title: "Все"}].concat(client.memoryKinds)
                delegate: MemoryButton {
                    required property var modelData
                    text: modelData.title; primary: page.activeKind === modelData.id
                    onClicked: page.activeKind = modelData.id
                }
            }
        }
        UiNotice {
            theme: page.theme; Layout.fillWidth: true
            error: !client.online || client.memoryError.length > 0
            text: !client.online ? (client.memories.length > 0 ? "Нет подключения. Показаны последние загруженные записи." : "Нет подключения к Scott.") : client.memoryError.length > 0 ? client.memoryError : client.memoryNotice
        }
        RowLayout {
            Text { font.family: page.theme.fontFamily; text: "Записи · " + page.filtered.length; color: page.muted; font.pixelSize: 12 }
            Item { Layout.fillWidth: true }
            Text { font.family: page.theme.fontFamily; text: "Ответов в истории · " + client.archivedTurns; visible: client.archivedTurns >= 0; color: page.muted; font.pixelSize: 12 }
            MemoryButton { text: "Очистить историю"; enabled: client.online && !client.memoryBusy && client.archivedTurns > 0; onClicked: confirmClearHistory.open() }
        }
        SurfacePanel {
            theme: page.theme
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 100
            radius: page.theme.cardRadius; color: page.surface; border.color: page.line
            Column {
                anchors.centerIn: parent; spacing: 10; visible: page.filtered.length === 0
                Text { font.family: page.theme.fontFamily; anchors.horizontalCenter: parent.horizontalCenter; text: client.memoryBusy ? "Загружаю память…" : !client.online ? "Подключите Scott" : client.memoryError.length > 0 ? "Не удалось загрузить записи" : client.memories.length === 0 ? "Здесь появится то, что важно вам" : "Ничего не найдено"; color: page.ink; font.pixelSize: 15 }
                Text { font.family: page.theme.fontFamily; anchors.horizontalCenter: parent.horizontalCenter; text: !client.online ? "Запустите backend на главной странице." : client.memoryError.length > 0 ? "Повторите загрузку кнопкой «Обновить»." : client.memories.length === 0 ? "Добавьте первый факт или предпочтение выше." : "Попробуйте другую категорию или запрос."; color: page.muted; font.pixelSize: 12 }
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
                    width: ListView.view.width; height: memoryBody.implicitHeight + 32
                    radius: page.theme.controlRadius; color: memoryHover.hovered ? page.elevated : page.bg
                    border.color: memoryHover.hovered ? Qt.alpha(page.accent, 0.45) : page.line
                    HoverHandler { id: memoryHover }
                    Behavior on color { enabled: page.theme.motion; ColorAnimation { duration: 160 } }
                    Behavior on border.color { enabled: page.theme.motion; ColorAnimation { duration: 160 } }
                    RowLayout {
                        id: memoryBody
                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 16
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 7
                            Text { font.family: page.theme.fontFamily; text: (memory.modelData.source === "conversation" ? "Из диалога · " : "") + page.categoryName(memory.modelData.kind) + "  ·  " + page.dateLabel(memory.modelData.updated || memory.modelData.created); color: page.accent; font.pixelSize: 11 }
                            TextEdit { font.family: page.theme.fontFamily; Layout.fillWidth: true; text: memory.modelData.text; readOnly: true; selectByMouse: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap; color: page.ink; font.pixelSize: 14 }
                        }
                        MemoryButton {
                            text: "Забыть"; destructive: true; enabled: client.online && !client.memoryBusy
                            onClicked: { page.pendingId = memory.modelData.id; page.pendingText = memory.modelData.text; confirmForget.open() }
                        }
                    }
                }
            }
        }
    }
    Dialog {
        id: confirmClearHistory
        objectName: "confirmClearHistory"
        parent: Overlay.overlay; anchors.centerIn: parent; modal: true; padding: 24
        width: Math.min(460, parent.width - 64)
        background: SurfacePanel { theme: page.theme; color: page.theme.popup }
        contentItem: ColumnLayout {
            spacing: 18
            Text { text: "Очистить историю разговоров?"; color: page.ink; font.pixelSize: 18; font.family: page.theme.fontFamily; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Text { text: "Scott забудет прошлые диалоги. Факты и предпочтения из списка останутся."; color: page.muted; font.family: page.theme.fontFamily; Layout.fillWidth: true; wrapMode: Text.Wrap }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                MemoryButton { text: "Отмена"; onClicked: confirmClearHistory.close() }
                MemoryButton { text: "Очистить"; destructive: true; onClicked: { client.clearConversationMemory(); confirmClearHistory.close() } }
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
            Text { font.family: page.theme.fontFamily; text: "Забыть эту запись?"; color: page.ink; font.pixelSize: 21; font.weight: Font.DemiBold }
            Text { font.family: page.theme.fontFamily; text: page.pendingText; color: page.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
            Text { font.family: page.theme.fontFamily; text: "Факт будет удалён из памяти. Исходные диалоги очищаются отдельно кнопкой «Очистить историю»."; color: page.muted; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
            RowLayout {
                Layout.alignment: Qt.AlignRight; spacing: 10
                MemoryButton { text: "Отмена"; onClicked: confirmForget.close() }
                MemoryButton { text: "Забыть запись"; primary: true; destructive: true; enabled: client.online && !client.memoryBusy; onClicked: { client.forgetMemory(page.pendingId); confirmForget.close() } }
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
