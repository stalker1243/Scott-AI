import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: page
    required property var client
    required property var files
    required property QtObject theme
    property int section: 0
    property string listFilter: "all"
    property string editId: ""
    property string nameDraft: ""
    property string descriptionDraft: ""
    property string phrasesDraft: ""
    property string scheduleDraft: ""
    property int repeatDraft: 1
    property bool enabledDraft: true
    property bool stopDraft: true
    property bool dirty: false
    property var pendingAction: null
    property var pendingDelete: ({})
    readonly property var filtered: client.protocols.filter(function(record) {
        const query = search.text.trim().toLocaleLowerCase()
        return (listFilter === "all" || listFilter === "enabled" && record.enabled || listFilter === "disabled" && !record.enabled || listFilter === "scheduled" && record.schedule_text.length)
            && (!query.length || [record.name, record.description, record.schedule_text].concat(record.phrases, record.steps.map(function(step) { return step.text })).join(" ").toLocaleLowerCase().indexOf(query) >= 0)
    })
    readonly property int resultCount: filtered.length
    readonly property string draftIssue: {
        if (!nameDraft.trim().length) return "Введите имя протокола"
        if (nameDraft.trim().length > 100) return "Имя — до 100 символов"
        if (descriptionDraft.length > 2000) return "Описание — до 2000 символов"
        if (!steps.count || steps.count > 40) return "Нужно от 1 до 40 шагов"
        let active = false
        for (let i = 0; i < steps.count; ++i) {
            const item = steps.get(i)
            if (!item.phrase.trim().length) return "Заполните шаг " + (i + 1)
            if (item.phrase.length > 2000) return "Шаг " + (i + 1) + " — до 2000 символов"
            if (!Number.isFinite(item.pauseSeconds) || item.pauseSeconds < 0 || item.pauseSeconds > 60) return "Пауза шага " + (i + 1) + ": от 0 до 60 с"
            active = active || item.active
        }
        if (!active) return "Включите хотя бы один шаг"
        if (splitLines(phrasesDraft).length > 20) return "Голосовых фраз — до 20"
        if (!splitLines(phrasesDraft).every(function(phrase) { return phrase.length <= 200 })) return "Голосовая фраза — до 200 символов"
        return ""
    }
    readonly property bool validDraft: draftIssue.length === 0
    readonly property var templates: [
        {name:"Рабочий день", description:"Подготовить рабочее пространство", steps:[{text:"открой браузер", pause:2}, {text:"открой редактор кода", pause:2}, {text:"приглуши звук", pause:0}]},
        {name:"Фокус", description:"Сосредоточиться на задаче", steps:[{text:"приглуши звук", pause:0}, {text:"напомни через 25 минут сделать перерыв", pause:0}]},
        {name:"Учёба", description:"Начать занятие", steps:[{text:"открой браузер", pause:2}, {text:"открой документы", pause:0}, {text:"напомни через час сделать перерыв", pause:0}]}
    ]
    spacing: 10
    ListModel { id: steps }
    function splitLines(text) { return text.replace(/\r/g, "").split("\n").map(function(line) { return line.trim() }).filter(function(line) { return line.length }) }
    function payload() {
        const result = []
        for (let i = 0; i < steps.count; ++i) { const step = steps.get(i); result.push({text:step.phrase.trim(), pause:step.pauseSeconds, enabled:step.active}) }
        return {name:nameDraft.trim(), description:descriptionDraft.trim(), phrases:splitLines(phrasesDraft), schedule:scheduleDraft.trim(),
                enabled:enabledDraft, repeat_count:repeatDraft, stop_on_error:stopDraft, steps:result}
    }
    function addStep(phrase) {
        if (steps.count >= 40) return
        steps.append({phrase:phrase || "", pauseSeconds:0, active:true}); dirty = true
    }
    function cloneStep(index) {
        if (steps.count >= 40) return
        const source = steps.get(index)
        steps.insert(index + 1, {phrase:source.phrase, pauseSeconds:source.pauseSeconds, active:source.active}); dirty = true
    }
    function loadDraft(record, copy) {
        editId = copy ? "" : (record.id || "")
        nameDraft = (record.name || "") + (copy && record.id ? " (копия)" : "")
        descriptionDraft = record.description || ""; phrasesDraft = (record.phrases || []).join("\n")
        scheduleDraft = copy ? "" : (typeof record.schedule === "string" ? record.schedule : record.schedule_text || "")
        repeatDraft = record.repeat_count || 1; enabledDraft = copy ? false : record.enabled !== false
        stopDraft = record.stop_on_error !== false
        steps.clear()
        for (const step of record.steps || []) steps.append({phrase:step.text, pauseSeconds:step.pause || 0, active:step.enabled !== false})
        if (!steps.count) steps.append({phrase:"", pauseSeconds:0, active:true})
        dirty = copy || !editId.length; section = 1
        Qt.callLater(function() { editorScroll.contentItem.contentY = 0 })
    }
    function perform(action) {
        if (client.protocolsBusy) return
        const meaningful = nameDraft.length || descriptionDraft.length || phrasesDraft.length || scheduleDraft.length || payload().steps.some(function(step) { return step.text.length })
        if (dirty && meaningful) { pendingAction = action; discardDialog.open() } else action()
    }
    function edit(record, copy) { perform(function() { loadDraft(record, copy) }) }
    function cancelDraft() {
        const record = client.protocols.find(function(item) { return item.id === page.editId })
        if (record) loadDraft(record, false)
        else { dirty = false; section = 0 }
    }
    function run(record) { client.runProtocol(record.id); section = 2 }
    Connections {
        target: page.client
        function onProtocolSaved(record) { page.loadDraft(record, false) }
        function onProtocolDeleted(id) { if (id === page.editId) { page.editId = ""; page.dirty = false; page.section = 0 } }
    }
    Connections { target: page.files; function onImported(record) { page.loadDraft(record, true) } }
    component SmallButton: UiButton { theme: page.theme; implicitHeight: 34; leftPadding: 12; rightPadding: 12; font.pixelSize: 12 }
    component Label: Text { font.family: page.theme.fontFamily; color: page.theme.muted; font.pixelSize: 12; textFormat: Text.PlainText }
    component Field: TextField {
        font.family: page.theme.fontFamily; font.pixelSize: 13; color: page.theme.ink; placeholderTextColor: page.theme.muted
        selectByMouse: true; hoverEnabled: true; implicitHeight: 38; leftPadding: 12; rightPadding: 12
        selectionColor: page.theme.accent; selectedTextColor: page.theme.accentText
        background: FieldSurface { theme: page.theme; focused: parent.activeFocus; hovered: parent.hovered }
    }
    component Area: TextArea {
        font.family: page.theme.fontFamily; font.pixelSize: 13; color: page.theme.ink; placeholderTextColor: page.theme.muted
        textFormat: TextEdit.PlainText; selectByMouse: true; wrapMode: TextEdit.Wrap; padding: 10
        implicitHeight: Math.max(56, contentHeight + 20)
        selectionColor: page.theme.accent; selectedTextColor: page.theme.accentText
        background: FieldSurface { theme: page.theme; focused: parent.activeFocus }
    }
    component Card: SurfacePanel {
        theme: page.theme; Layout.fillWidth: true
        default property alias content: body.data
        implicitHeight: body.implicitHeight + 28
        data: ColumnLayout { id: body; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 8 }
    }
    component Modal: Dialog {
        id:modal
        parent:Overlay.overlay; anchors.centerIn:parent; modal:true; padding:16
        background:Rectangle { color:page.theme.popup; radius:page.theme.cardRadius; border.color:page.theme.line }
        header:Label { text:modal.title; color:page.theme.ink; font.pixelSize:14; font.weight:Font.DemiBold; leftPadding:16; rightPadding:16; topPadding:14; bottomPadding:10; wrapMode:Text.WordWrap }
        enter:Transition { enabled:page.theme.motion; NumberAnimation { property:"opacity"; from:0; to:1; duration:130 } }
        exit:Transition { enabled:page.theme.motion; NumberAnimation { property:"opacity"; to:0; duration:90 } }
    }
    RowLayout {
        UiSegmentedControl { objectName:"protocolSections"; theme:page.theme; model:["Список", "Редактор", "Запуск"]; currentIndex:page.section; Layout.fillWidth:true; Layout.minimumWidth:0; implicitHeight:42; onActivated:function(index) { page.section = index } }
        SmallButton { objectName:"newProtocol"; text:"+"; implicitWidth:36; enabled:!client.protocolsBusy; Accessible.name:"Новый протокол"; ToolTip.visible:hovered; ToolTip.text:"Новый протокол"; onClicked:page.edit({}, false) }
        SmallButton { text:"Импорт"; enabled:!client.protocolsBusy; onClicked:page.perform(function() { files.chooseImport() }) }
        SmallButton { objectName:"refreshProtocols"; text:"↻"; implicitWidth:36; Accessible.name:"Обновить протоколы"; enabled:client.online && !client.protocolsBusy; onClicked:client.refreshProtocols() }
    }
    UiNotice { theme:page.theme; Layout.fillWidth:true; error:true; text:client.protocolsError || client.protocolJobError || files.error }
    UiNotice { theme:page.theme; Layout.fillWidth:true; text:!client.online ? "Scott не подключён. Черновик сохранится в окне." : client.protocolsNotice || files.notice }
    StackLayout {
        Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:0; currentIndex:page.section
        ColumnLayout {
            spacing:10
            Field { id:search; objectName:"protocolSearch"; Layout.fillWidth:true; placeholderText:"Найти протокол, фразу или шаг…" }
            Flow {
                Layout.fillWidth:true; spacing:6
                Repeater { model:[{id:"all", title:"Все"}, {id:"enabled", title:"Активные"}, {id:"scheduled", title:"По расписанию"}, {id:"disabled", title:"Отключённые"}]
                    SmallButton { required property var modelData; text:modelData.title; primary:page.listFilter === modelData.id; onClicked:page.listFilter = modelData.id }
                }
            }
            Item {
                Layout.fillWidth:true; Layout.fillHeight:true
                ColumnLayout {
                    anchors.centerIn:parent; width:parent.width - 24; visible:page.filtered.length === 0; spacing:12
                    Label { Layout.alignment:Qt.AlignHCenter; text:client.protocolsBusy ? "Загружаю протоколы…" : search.text.length || page.listFilter !== "all" ? "Ничего не найдено" : "Создайте первый протокол"; font.pixelSize:15 }
                    Flow { Layout.fillWidth:true; spacing:8; visible:!search.text.length && page.listFilter === "all"
                        Repeater { model:page.templates; SmallButton { required property var modelData; required property int index; objectName:"protocolEmptyTemplate" + index; text:modelData.name; onClicked:page.edit(modelData, true) } }
                    }
                }
                ListView {
                    objectName:"protocolList"; anchors.fill:parent; anchors.rightMargin:12; clip:true; spacing:10; model:page.filtered; visible:page.filtered.length > 0
                    boundsBehavior:Flickable.StopAtBounds; ScrollBar.vertical:UiScrollBar { theme:page.theme }
                    delegate:SurfacePanel {
                        required property var modelData
                        width:ListView.view.width; implicitHeight:rowBody.implicitHeight + 28; theme:page.theme
                        ColumnLayout {
                            id:rowBody; anchors.left:parent.left; anchors.right:parent.right; anchors.top:parent.top; anchors.margins:14; spacing:7
                            RowLayout {
                                Label { Layout.fillWidth:true; Layout.minimumWidth:0; text:modelData.name; color:page.theme.ink; font.pixelSize:15; font.weight:Font.DemiBold; wrapMode:Text.WordWrap }
                                Label { text:modelData.enabled ? "● Активен" : "○ Отключён"; color:modelData.enabled ? page.theme.accent : page.theme.muted }
                            }
                            Label { Layout.fillWidth:true; text:modelData.description; visible:text.length > 0; wrapMode:Text.WordWrap }
                            Label { Layout.fillWidth:true; text:modelData.steps.length + " шагов · " + (modelData.repeat_count || 1) + "× · " + modelData.runs + " запусков" }
                            Label { Layout.fillWidth:true; text:modelData.schedule_text.length ? modelData.schedule_text : "По запросу: протокол «" + modelData.name + "»"; color:page.theme.accent; wrapMode:Text.WordWrap }
                            Flow {
                                Layout.fillWidth:true; spacing:6
                                SmallButton { objectName:"runProtocol_" + modelData.id; text:"Запустить"; primary:true; enabled:client.online && client.protocolsReady && !client.protocolsBusy && client.protocolJobReady && !client.protocolRunning && !client.protocolJobBusy && modelData.enabled; onClicked:page.run(modelData) }
                                SmallButton { objectName:"editProtocol_" + modelData.id; text:"Изменить"; enabled:!client.protocolsBusy; onClicked:page.edit(modelData, false) }
                                SmallButton { text:"Копия"; enabled:!client.protocolsBusy; onClicked:page.edit(modelData, true) }
                                SmallButton { text:"Удалить"; destructive:true; enabled:client.online && client.protocolsReady && !client.protocolsBusy && !(client.protocolRunning && client.protocolJob.protocol_id === modelData.id); onClicked: { page.pendingDelete = modelData; deleteDialog.open() } }
                            }
                        }
                    }
                }
            }
        }
        ColumnLayout {
            spacing:10
            ScrollView {
                id:editorScroll; objectName:"protocolEditorScroll"; Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:0
                contentWidth:availableWidth; rightPadding:12; clip:true
                ScrollBar.vertical:UiScrollBar { theme:page.theme; parent:editorScroll; x:editorScroll.width - width; height:editorScroll.availableHeight }
                ColumnLayout {
                    width:editorScroll.availableWidth; spacing:12
                    Flow {
                        Layout.fillWidth:true; spacing:6; visible:!page.editId.length && !page.nameDraft.length
                        Repeater { model:page.templates; SmallButton { required property var modelData; text:modelData.name; enabled:!client.protocolsBusy; onClicked:page.edit(modelData, true) } }
                    }
                    Card {
                        Field { objectName:"protocolName"; Layout.fillWidth:true; placeholderText:"Имя протокола"; text:page.nameDraft; enabled:!client.protocolsBusy; onTextEdited: { page.nameDraft = text; page.dirty = true } }
                        Field { Layout.fillWidth:true; placeholderText:"Описание"; text:page.descriptionDraft; enabled:!client.protocolsBusy; onTextEdited: { page.descriptionDraft = text; page.dirty = true } }
                        RowLayout {
                            UiSwitch { theme:page.theme; text:"Активен"; checked:page.enabledDraft; enabled:!client.protocolsBusy; onToggled: { page.enabledDraft = checked; page.dirty = true } }
                            Item { Layout.fillWidth:true }
                            Label { text:"Повторы" }
                            UiComboBox { objectName:"protocolRepeat"; theme:page.theme; Layout.preferredWidth:85; implicitHeight:36; model:Array.from({length:20}, function(_, i) { return (i + 1) + "×" }); currentIndex:page.repeatDraft - 1; enabled:!client.protocolsBusy; onActivated: { page.repeatDraft = currentIndex + 1; page.dirty = true } }
                        }
                        UiSwitch { objectName:"protocolStopOnError"; theme:page.theme; text:"Остановиться при ошибке"; checked:page.stopDraft; enabled:!client.protocolsBusy; onToggled: { page.stopDraft = checked; page.dirty = true } }
                    }
                    RowLayout {
                        Label { text:"Шаги · " + steps.count + " / 40"; font.weight:Font.DemiBold; Layout.fillWidth:true }
                        SmallButton { text:"Из действий"; enabled:steps.count < 40 && !client.protocolsBusy; onClicked:actionsDialog.open() }
                        SmallButton { text:"Вставить список"; enabled:steps.count < 40 && !client.protocolsBusy; onClicked:bulkDialog.open() }
                    }
                    Repeater {
                        model:steps
                        Card {
                            id:stepCard
                            required property int index
                            required property string phrase
                            required property real pauseSeconds
                            required property bool active
                            RowLayout {
                                Label { text:"Шаг " + (stepCard.index + 1); Layout.fillWidth:true }
                                UiSwitch { theme:page.theme; checked:stepCard.active; implicitHeight:30; Accessible.name:"Включить шаг " + (stepCard.index + 1); enabled:!client.protocolsBusy; onToggled: { steps.setProperty(stepCard.index, "active", checked); page.dirty = true } }
                                SmallButton { text:"↑"; implicitWidth:30; leftPadding:4; rightPadding:4; Accessible.name:"Переместить шаг вверх"; enabled:stepCard.index > 0 && !client.protocolsBusy; onClicked: { steps.move(stepCard.index, stepCard.index - 1, 1); page.dirty = true } }
                                SmallButton { text:"↓"; implicitWidth:30; leftPadding:4; rightPadding:4; Accessible.name:"Переместить шаг вниз"; enabled:stepCard.index < steps.count - 1 && !client.protocolsBusy; onClicked: { steps.move(stepCard.index, stepCard.index + 1, 1); page.dirty = true } }
                                SmallButton { text:"⧉"; implicitWidth:30; leftPadding:4; rightPadding:4; Accessible.name:"Копировать шаг"; enabled:steps.count < 40 && !client.protocolsBusy; onClicked:page.cloneStep(stepCard.index) }
                                SmallButton { text:"×"; implicitWidth:30; leftPadding:4; rightPadding:4; destructive:true; Accessible.name:"Удалить шаг"; enabled:!client.protocolsBusy; onClicked: { steps.remove(stepCard.index); page.dirty = true } }
                            }
                            Area { objectName:"protocolStep" + stepCard.index; Layout.fillWidth:true; placeholderText:"Команда словами, например «открой браузер»"; text:stepCard.phrase; enabled:stepCard.active && !client.protocolsBusy; onTextChanged:if (activeFocus) { steps.setProperty(stepCard.index, "phrase", text); page.dirty = true } }
                            RowLayout {
                                Label { text:"Пауза после шага, с"; Layout.fillWidth:true }
                                Field { Layout.preferredWidth:85; implicitHeight:32; text:stepCard.pauseSeconds.toString(); enabled:!client.protocolsBusy; validator:DoubleValidator { bottom:0; top:60; decimals:2; locale:"C" } onTextEdited: { steps.setProperty(stepCard.index, "pauseSeconds", Number(text.replace(",", "."))); page.dirty = true } }
                            }
                        }
                    }
                    SmallButton { objectName:"addProtocolStep"; text:"+ Добавить шаг"; enabled:steps.count < 40 && !client.protocolsBusy; onClicked:page.addStep("") }
                    Card {
                        Label { text:"Голос и расписание"; color:page.theme.ink; font.weight:Font.DemiBold }
                        Area { Layout.fillWidth:true; placeholderText:"Дополнительные фразы запуска — по одной на строку"; text:page.phrasesDraft; enabled:!client.protocolsBusy; onTextChanged:if (activeFocus) { page.phrasesDraft = text; page.dirty = true } }
                        Field { objectName:"protocolSchedule"; Layout.fillWidth:true; placeholderText:"По запросу; или «пн, ср, пт в 18:00»"; text:page.scheduleDraft; enabled:!client.protocolsBusy; onTextEdited: { page.scheduleDraft = text; page.dirty = true } }
                        Flow { Layout.fillWidth:true; spacing:6
                            Repeater { model:["по будням в 09:00", "каждый день в 23:00", "по выходным в 11:00"]
                                SmallButton { required property string modelData; text:modelData; enabled:!client.protocolsBusy; onClicked: { page.scheduleDraft = modelData; page.dirty = true } }
                            }
                            SmallButton { text:"По запросу"; enabled:!client.protocolsBusy; onClicked: { page.scheduleDraft = ""; page.dirty = true } }
                        }
                    }
                }
            }
            RowLayout {
                Label { Layout.fillWidth:true; Layout.minimumWidth:0; wrapMode:Text.WordWrap; text:page.draftIssue || (page.dirty ? "Есть изменения" : page.editId.length ? "Сохранено" : "Новый протокол"); color:page.draftIssue.length ? page.theme.danger : page.theme.muted }
                SmallButton { text:"Экспорт"; enabled:page.validDraft; onClicked:files.chooseExport(JSON.stringify(page.payload())) }
                SmallButton { text:"Отмена"; enabled:!client.protocolsBusy; onClicked:page.cancelDraft() }
                SmallButton { objectName:"saveProtocol"; text:client.protocolsBusy ? "Сохранение…" : "Сохранить"; primary:true; enabled:client.online && client.protocolsReady && !client.protocolsBusy && page.validDraft && page.dirty; onClicked:client.saveProtocol(page.editId, JSON.stringify(page.payload())) }
            }
        }
        ColumnLayout {
            spacing:10
            Card {
                Label { text:client.protocolJob.name || "Запуск протокола"; color:page.theme.ink; font.pixelSize:15; font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                Label { Layout.fillWidth:true; wrapMode:Text.WordWrap; text:client.protocolJob.message || "Запустите сохранённый протокол из списка." }
                Label { Layout.fillWidth:true; wrapMode:Text.WordWrap; visible:client.protocolRunning; text:(client.protocolJob.current || 0) + " / " + (client.protocolJob.total || 0) + " · " + (client.protocolJob.text || "Ожидание начала") }
                Rectangle {
                    Layout.fillWidth:true; height:4; radius:2; color:page.theme.elevated; visible:client.protocolJob.total > 0
                    Rectangle { width:parent.width * (client.protocolJob.current || 0) / Math.max(1, client.protocolJob.total || 1); height:parent.height; radius:2; color:page.theme.accent; Behavior on width { enabled:page.theme.motion; NumberAnimation { duration:180 } } }
                }
                SmallButton { objectName:"cancelProtocol"; text:client.protocolJob.state === "cancelling" ? "Останавливаю…" : "Остановить"; destructive:true; visible:client.protocolRunning; enabled:client.online && !client.protocolJobBusy && client.protocolJob.state !== "cancelling"; onClicked:client.cancelProtocol() }
                Label { visible:client.protocolRunning; text:"Остановка прервёт дальнейшие шаги. Завершённые действия сохранятся."; Layout.fillWidth:true; wrapMode:Text.WordWrap }
            }
            ListView {
                objectName:"protocolResults"; Layout.fillWidth:true; Layout.fillHeight:true; clip:true; spacing:8
                model:client.protocolJob.steps || []; boundsBehavior:Flickable.StopAtBounds
                ScrollBar.vertical:UiScrollBar { theme:page.theme }
                delegate:SurfacePanel {
                    required property var modelData
                    required property int index
                    theme:page.theme; width:ListView.view.width - 12; implicitHeight:resultBody.implicitHeight + 24
                    ColumnLayout {
                        id:resultBody; anchors.left:parent.left; anchors.right:parent.right; anchors.top:parent.top; anchors.margins:12; spacing:6
                        Label { Layout.fillWidth:true; wrapMode:Text.WordWrap; text:(modelData.ok ? "✓ " : "× ") + (index + 1) + ". " + modelData.text + (modelData.iteration > 1 ? " · повтор " + modelData.iteration : ""); color:modelData.ok ? page.theme.accent : page.theme.danger }
                        TextEdit { Layout.fillWidth:true; text:modelData.response; visible:text.length > 0; textFormat:TextEdit.PlainText; color:page.theme.ink; font.family:page.theme.fontFamily; font.pixelSize:12; readOnly:true; selectByMouse:true; wrapMode:TextEdit.Wrap }
                    }
                }
            }
        }
    }
    Modal {
        id:discardDialog; objectName:"discardProtocolDraft"; parent:Overlay.overlay; anchors.centerIn:parent
        width:Math.min(440, parent.width - 32); modal:true; padding:18; title:"Оставить изменения?"
        background:Rectangle { color:page.theme.popup; radius:page.theme.cardRadius; border.color:page.theme.line }
        contentItem:Label { text:"Несохранённый черновик будет заменён."; wrapMode:Text.WordWrap }
        palette.windowText:page.theme.ink
        footer:RowLayout { spacing:8; SmallButton { text:"Продолжить правку"; Layout.fillWidth:true; onClicked:discardDialog.close() } SmallButton { text:"Заменить"; destructive:true; onClicked: { discardDialog.close(); const action = page.pendingAction; page.pendingAction = null; if (action) action() } } }
    }
    Modal {
        id:deleteDialog; objectName:"confirmDeleteProtocol"; parent:Overlay.overlay; anchors.centerIn:parent
        width:Math.min(440, parent.width - 32); modal:true; padding:18; title:"Удалить протокол?"
        background:Rectangle { color:page.theme.popup; radius:page.theme.cardRadius; border.color:page.theme.line }
        contentItem:Label { text:page.pendingDelete.name || ""; wrapMode:Text.WordWrap }
        palette.windowText:page.theme.ink
        footer:RowLayout { SmallButton { text:"Отмена"; Layout.fillWidth:true; onClicked:deleteDialog.close() } SmallButton { objectName:"deleteProtocolConfirmed"; text:"Удалить"; destructive:true; enabled:client.online && client.protocolsReady && !client.protocolsBusy; onClicked: { client.deleteProtocol(page.pendingDelete.id); deleteDialog.close() } } }
    }
    Modal {
        id:actionsDialog; objectName:"protocolActionsDialog"; parent:Overlay.overlay; anchors.centerIn:parent
        width:Math.min(680, parent.width - 32); height:Math.min(520, parent.height - 32); modal:true; padding:16; title:"Добавить команду"
        palette.windowText:page.theme.ink
        background:Rectangle { color:page.theme.popup; radius:page.theme.cardRadius; border.color:page.theme.line }
        contentItem:ActionsPage { client:page.client; theme:page.theme; onPhraseRequested:function(phrase) { page.addStep(phrase); actionsDialog.close() } }
        footer:SmallButton { text:"Закрыть"; onClicked:actionsDialog.close() }
    }
    Modal {
        id:bulkDialog; objectName:"protocolBulkDialog"; parent:Overlay.overlay; anchors.centerIn:parent
        width:Math.min(580, parent.width - 32); height:Math.min(360, parent.height - 32); modal:true; padding:16; title:"Команды — по одной на строку"
        background:Rectangle { color:page.theme.popup; radius:page.theme.cardRadius; border.color:page.theme.line }
        contentItem:ScrollView { clip:true; contentWidth:availableWidth; Area { id:bulkText; objectName:"protocolBulkText"; width:parent.width; placeholderText:"открой браузер\nоткрой документы" } }
        palette.windowText:page.theme.ink
        footer:RowLayout { SmallButton { text:"Отмена"; Layout.fillWidth:true; onClicked:bulkDialog.close() } SmallButton { objectName:"protocolBulkAdd"; text:"Добавить"; primary:true; enabled:page.splitLines(bulkText.text).length > 0 && page.splitLines(bulkText.text).length + steps.count <= 40; onClicked: { for (const phrase of page.splitLines(bulkText.text)) page.addStep(phrase); bulkText.text = ""; bulkDialog.close() } } }
    }
}
