import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    required property var client
    required property QtObject theme
    property string activeGroup: ""
    property bool readyOnly: false
    readonly property var categories: ["Все категории"].concat(client.abilities.map(function(group) { return group.group }))
    readonly property var filtered: {
        const query = search.text.trim().toLocaleLowerCase()
        const result = []
        for (const group of client.abilities) {
            if (activeGroup.length && group.group !== activeGroup) continue
            for (const item of group.items) {
                if (readyOnly && item.state !== "ready") continue
                const words = [group.group, item.title, item.detail, item.reason].concat(item.examples).join(" ").toLocaleLowerCase()
                if (query.length && words.indexOf(query) < 0) continue
                result.push({id: item.id, group: group.group, title: item.title, detail: item.detail,
                                state: item.state, reason: item.reason, examples: item.examples})
            }
        }
        return result
    }
    signal phraseRequested(string phrase)
    readonly property int resultCount: filtered.length
    onFilteredChanged: Qt.callLater(function() { actionList.positionViewAtBeginning() })
    Connections {
        target: page.client
        function onAbilitiesChanged() {
            if (page.activeGroup.length && page.categories.indexOf(page.activeGroup) < 0) page.activeGroup = ""
            category.currentIndex = Math.max(0, page.categories.indexOf(page.activeGroup))
        }
    }
    component ActionButton: UiButton {
        theme: page.theme
        implicitHeight: 36; leftPadding: 12; rightPadding: 12; font.pixelSize: 12
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 10
        RowLayout {
            spacing: 10
            TextField {
                id: search; objectName: "actionsSearch"
                Layout.fillWidth: true; implicitHeight: 40
                font.family: page.theme.fontFamily; font.pixelSize: 13
                color: page.theme.ink; placeholderTextColor: page.theme.muted
                placeholderText: "Найти действие или фразу…"
                selectByMouse: true; hoverEnabled: true; leftPadding: 38; rightPadding: 38
                selectionColor: page.theme.accent; selectedTextColor: page.theme.accentText
                background: FieldSurface { theme: page.theme; fill: page.theme.surface; focused: search.activeFocus; hovered: search.hovered }
                NavIcon { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 17; height: 17; symbol: 5; color: search.activeFocus ? page.theme.accent : page.theme.muted }
                ActionButton {
                    anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                    width: 30; implicitHeight: 30; leftPadding: 0; rightPadding: 0; text: "×"
                    Accessible.name: "Очистить поиск"; visible: search.text.length > 0
                    onClicked: { search.clear(); search.forceActiveFocus() }
                }
            }
            ActionButton {
                objectName: "refreshActions"; text: client.abilitiesBusy ? "Загрузка…" : "Обновить"
                enabled: client.online && !client.abilitiesBusy
                onClicked: client.refreshAbilities()
            }
        }
        RowLayout {
            spacing: 10
            UiComboBox {
                id: category; objectName: "actionsCategory"; theme: page.theme
                Layout.preferredWidth: 205; implicitHeight: 36; font.pixelSize: 12
                model: page.categories
                Accessible.name: "Категория действий"
                onActivated: page.activeGroup = currentIndex === 0 ? "" : currentText
            }
            ActionButton {
                objectName: "actionsReadyOnly"; text: "Доступные"; checkable: true
                checked: page.readyOnly; primary: checked
                onClicked: page.readyOnly = checked
                Accessible.name: "Показать только доступные действия"
            }
            Item { Layout.fillWidth: true }
            Text {
                objectName: "actionsSummary"
                text: client.abilitiesReady ? client.abilitiesReadyCount + " из " + client.abilitiesTotal + " доступны" : client.abilitiesBusy ? "Проверяю…" : "Список не обновлён"
                color: page.theme.muted; font.family: page.theme.fontFamily; font.pixelSize: 12
            }
        }
        UiNotice {
            theme: page.theme; Layout.fillWidth: true; error: true
            text: !client.online ? (client.abilities.length ? "Нет подключения. Показан последний список действий." : "Подключите Scott, чтобы загрузить действия.") : client.abilitiesError
        }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 100
            Text {
                objectName: "actionsEmpty"; anchors.centerIn: parent; width: parent.width - 32
                visible: page.filtered.length === 0
                text: client.abilitiesBusy ? "Загружаю действия…" : !client.online ? "Scott не подключён" : !client.abilitiesReady ? "Список действий недоступен" : client.abilitiesTotal === 0 ? "Пока нет действий" : "Ничего не найдено"
                color: page.theme.muted; font.family: page.theme.fontFamily; font.pixelSize: 14
                wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
            }
            ListView {
                id: actionList; objectName: "actionsList"
                anchors.fill: parent; anchors.rightMargin: 12
                clip: true; spacing: 10; model: page.filtered
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: UiScrollBar { theme: page.theme }
                populate: Transition { enabled: page.theme.motion; NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160 } }
                delegate: Column {
                    id: entry
                    required property var modelData
                    required property int index
                    width: ListView.view.width; spacing: 8
                    readonly property bool ready: modelData.state === "ready"
                    Text {
                        visible: entry.index <= 0 || !page.filtered[entry.index - 1] || page.filtered[entry.index - 1].group !== entry.modelData.group
                        text: entry.modelData.group; color: page.theme.muted
                        font.family: page.theme.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold
                        topPadding: 4; bottomPadding: 6
                    }
                    SurfacePanel {
                        theme: page.theme; width: parent.width; implicitHeight: body.implicitHeight + 28
                        ColumnLayout {
                            id: body; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                            anchors.margins: 14; spacing: 7
                            RowLayout {
                                spacing: 10
                                Text {
                                    Layout.fillWidth: true; Layout.minimumWidth: 0
                                    text: entry.modelData.title; color: page.theme.ink
                                    font.family: page.theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    text: entry.ready ? "● Доступно" : "○ Недоступно"
                                    color: entry.ready ? page.theme.accent : page.theme.danger
                                    font.family: page.theme.fontFamily; font.pixelSize: 11
                                }
                            }
                            Text {
                                Layout.fillWidth: true; text: entry.modelData.detail; color: page.theme.muted
                                font.family: page.theme.fontFamily; font.pixelSize: 12; wrapMode: Text.WordWrap
                            }
                            Text {
                                objectName: "actionReason_" + entry.modelData.id
                                Layout.fillWidth: true; visible: !entry.ready
                                text: entry.modelData.reason.length ? entry.modelData.reason : "Действие недоступно на этой машине."
                                color: page.theme.danger; font.family: page.theme.fontFamily; font.pixelSize: 12; wrapMode: Text.WordWrap
                            }
                            Flow {
                                id: examples; Layout.fillWidth: true; visible: entry.ready; spacing: 6
                                Repeater {
                                    model: entry.ready ? entry.modelData.examples : []
                                    ActionButton {
                                        id: phraseButton
                                        required property string modelData
                                        required property int index
                                        objectName: "actionExample_" + entry.modelData.id + "_" + index
                                        text: modelData + " ↗"; width: Math.min(implicitWidth, examples.width)
                                        enabled: page.client.online && page.client.abilitiesReady && !page.client.abilitiesBusy
                                        Accessible.name: "Добавить в диалог: " + modelData
                                        ToolTip.visible: hovered; ToolTip.delay: 450
                                        ToolTip.text: "Добавить в черновик диалога"
                                        contentItem: Text {
                                            text: phraseButton.text; color: page.theme.ink; font: phraseButton.font
                                            elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
                                        }
                                        onClicked: if (enabled) page.phraseRequested(modelData)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
