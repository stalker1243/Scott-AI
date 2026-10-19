import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "CapabilityInfo.js" as CapabilityInfo

ColumnLayout {
    id: page
    required property var client
    required property QtObject theme
    property string providerId: ""
    property string selectedModel: ""
    property bool manualModel: false
    property bool dirty: false
    property bool syncing: false
    property bool showToken: false
    property string warningFeature: ""
    property alias apiToken: tokenField.text
    property alias customModel: customField.text
    property alias search: searchField.text
    readonly property var provider: client.aiProviders.find(function(p) { return p.id === providerId }) || ({})
    readonly property string modelId: (manualModel ? customField.text : selectedModel).trim()
    readonly property var selectedCapabilities: ((provider.models || []).find(function(m) { return m.id === modelId }) || {}).capabilities || ({})
    readonly property var choices: (provider.models || []).filter(function(m) {
        const query = searchField.text.trim().toLowerCase()
        return !query.length || m.id.toLowerCase().includes(query) || (m.note || "").toLowerCase().includes(query)
    }).map(function(m) { return {id:m.id, title:m.id + (m.free ? qsTranslate("Launcher", " · бесплатно") : ""), note:m.note || ""} })
    readonly property bool editable: client.online && client.modelsReady && !client.modelsBusy
    readonly property bool validDraft: provider.id !== undefined && modelId.length > 0 && modelId.length <= 200 &&
        !/[\s\x00-\x1f]/.test(modelId) && (provider.configured || tokenField.text.trim().length > 0) &&
        !/[\x00-\x1f]/.test(tokenField.text.trim())
    spacing: 10
    function providerIndex(id) { return client.aiProviders.findIndex(function(p) { return p.id === id }) }
    function modelIndex(id) { return choices.findIndex(function(m) { return m.id === id }) }
    function chooseProvider(id) {
        if (providerId === id) return
        syncing = true
        providerId = id; tokenField.clear(); showToken = false; searchField.clear()
        const row = client.aiProviders.find(function(p) { return p.id === id }) || ({})
        selectedModel = id === client.aiState.provider ? client.aiState.model || "" : ((row.models || [])[0] || {}).id || ""
        manualModel = selectedModel.length > 0 && !(row.models || []).some(function(m) { return m.id === selectedModel })
        customField.text = manualModel ? selectedModel : ""
        syncing = false; dirty = true
    }
    function syncDraft(force) {
        if (!client.modelsReady || (!force && dirty)) return
        const id = providerIndex(client.aiState.provider) >= 0 ? client.aiState.provider : (client.aiProviders[0] || {}).id || ""
        // Clearing the old provider first forces a complete reset after success.
        providerId = ""; chooseProvider(id); dirty = false
    }
    function apply() {
        if (editable && validDraft) client.configureModel(providerId, modelId, tokenField.text)
    }
    function revealField(field) {
        const y = field.mapToItem(formContent, 0, 0).y
        if (y < scroll.contentY + 8) scroll.contentY = Math.max(0, y - 8)
        else if (y + field.height > scroll.contentY + scroll.height - 8)
            scroll.contentY = Math.max(0, Math.min(scroll.contentHeight - scroll.height, y + field.height - scroll.height + 8))
    }
    Component.onCompleted: syncDraft(false)
    onVisibleChanged: if (!visible) showToken = false
    Connections {
        target: page.client
        function onModelsChanged() { page.syncDraft(false) }
        function onModelConfigured() { tokenField.clear(); page.showToken = false; page.syncDraft(true) }
    }
    component Label: Text {
        color: page.theme.ink; font.family: page.theme.fontFamily; font.pixelSize: 13
        textFormat: Text.PlainText; wrapMode: Text.Wrap; Layout.fillWidth: true
    }
    component Hint: Label { color: page.theme.muted; font.pixelSize: 12 }
    component Input: TextField {
        Layout.fillWidth: true; implicitHeight: 42; selectByMouse: true
        font.family: page.theme.fontFamily; color: page.theme.ink; placeholderTextColor: page.theme.muted
        leftPadding: 12; rightPadding: 12
        background: FieldSurface { theme: page.theme; focused: parent.activeFocus; hovered: parent.hovered }
        onActiveFocusChanged: if (activeFocus) page.revealField(this)
    }
    UiNotice { theme: page.theme; Layout.fillWidth: true; text: client.modelsError; error: true }
    UiNotice { theme: page.theme; Layout.fillWidth: true; text: client.modelsError.length || page.dirty ? "" : client.modelsNotice }
    Flickable {
        id: scroll
        objectName: "modelsScroll"
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
        clip: true; contentWidth: width; contentHeight: formContent.implicitHeight
        boundsBehavior: Flickable.StopAtBounds; flickableDirection: Flickable.VerticalFlick
        ScrollBar.vertical: UiScrollBar { theme: page.theme }
        ColumnLayout {
            id: formContent
            width: scroll.width - (scroll.contentHeight > scroll.height ? 12 : 0); spacing: 12
            SurfacePanel {
                flat: true
                theme: page.theme; Layout.fillWidth: true; implicitHeight: activeContent.implicitHeight + 28
                ColumnLayout {
                    id: activeContent
                    anchors.fill: parent; anchors.margins: 14; spacing: 6
                    RowLayout {
                        Label { text: qsTranslate("Launcher", "Используется"); color: page.theme.muted; font.pixelSize: 12 }
                        Label {
                            Layout.fillWidth: false
                            text: !client.online ? qsTranslate("Launcher", "Scott отключён") : !client.modelsReady ? qsTranslate("Launcher", "Нет данных") : client.aiState.enabled ? qsTranslate("Launcher", "Настроено") : qsTranslate("Launcher", "Не подключено")
                            color: client.online && client.modelsReady && client.aiState.enabled ? page.theme.success : page.theme.muted
                        }
                    }
                    Label {
                        text: client.aiState.provider ? client.aiState.provider + " · " + (client.aiState.model || "") : qsTranslate("Launcher", "Модель ещё не выбрана")
                        font.pixelSize: 16; font.weight: Font.DemiBold
                    }
                }
            }
            SurfacePanel {
                flat: true
                theme: page.theme; Layout.fillWidth: true; implicitHeight: connectionContent.implicitHeight + 28
                ColumnLayout {
                    id: connectionContent
                    anchors.fill: parent; anchors.margins: 14; spacing: 8
                    RowLayout {
                        Label { text: qsTranslate("Launcher", "Провайдер"); font.weight: Font.DemiBold }
                        Hint { Layout.fillWidth: false; text: page.provider.configured ? qsTranslate("Launcher", "Ключ настроен") : qsTranslate("Launcher", "Нужен API Token") }
                    }
                    UiComboBox {
                        objectName: "modelProvider"; theme: page.theme; Layout.fillWidth: true
                        model: client.aiProviders; textRole: "id"; translateDisplay: false; currentIndex: page.providerIndex(page.providerId)
                        enabled: page.editable
                        onActivated: function(index) { page.chooseProvider(model[index].id) }
                    }
                    Hint { text: qsTranslate("Launcher", page.provider.note || (client.modelsBusy ? qsTranslate("Launcher", "Загружаю провайдеров и модели…") : qsTranslate("Launcher", "Обновите данные для настройки подключения."))) }
                    RowLayout {
                        Label { text: qsTranslate("Launcher", "Модель"); font.weight: Font.DemiBold }
                        UiSwitch {
                            objectName: "manualModel"; theme: page.theme; text: qsTranslate("Launcher", "ID вручную")
                            checked: page.manualModel; enabled: page.editable
                            onToggled: {
                                page.manualModel = checked
                                if (checked && !customField.text.length) customField.text = page.selectedModel
                                page.dirty = true
                            }
                        }
                    }
                    Input {
                        id: searchField; objectName: "modelSearch"; visible: !page.manualModel; enabled: page.editable
                        placeholderText: qsTranslate("Launcher", "Поиск модели"); maximumLength: 200
                    }
                    UiComboBox {
                        objectName: "modelChoice"; theme: page.theme; Layout.fillWidth: true
                        model: page.choices; textRole: "title"; translateDisplay: false; currentIndex: page.modelIndex(page.selectedModel)
                        displayText: currentIndex >= 0 ? page.choices[currentIndex].title : page.selectedModel || qsTranslate("Launcher", "Нет моделей — укажите ID вручную")
                        enabled: page.editable && page.choices.length > 0; visible: !page.manualModel
                        onActivated: function(index) { page.selectedModel = model[index].id; page.dirty = true }
                    }
                    Input {
                        id: customField; objectName: "customModel"; visible: page.manualModel; enabled: page.editable
                        placeholderText: qsTranslate("Launcher", "ID модели у провайдера"); maximumLength: 200
                        onTextEdited: page.dirty = true
                    }
                    Hint {
                        visible: !page.manualModel
                        text: page.choices.length === 0 && searchField.text.length ? qsTranslate("Launcher", "Ничего не найдено. Измените поиск или укажите ID вручную.") :
                            qsTranslate("Launcher", ((page.provider.models || []).find(function(m) { return m.id === page.selectedModel }) || {}).note || qsTranslate("Launcher", "Можно указать модель, которой ещё нет в каталоге."))
                    }
                    CapabilityBadges { theme: page.theme; Layout.fillWidth: true; capabilities: page.selectedCapabilities; onFeatureRequested: function(feature) { page.warningFeature = feature } }
                    UiNotice { theme: page.theme; Layout.fillWidth: true; warning: true; text: page.warningFeature.length ? CapabilityInfo.reason({model:page.modelId, capabilities:page.selectedCapabilities}, page.warningFeature) : "" }
                    Hint { text: page.selectedCapabilities.known ? qsTranslate("Launcher", "Файлы: текст из PDF, DOCX и исходного кода. Возможности и доступ зависят от API модели.") : qsTranslate("Launcher", "Возможности этой модели не подтверждены каталогом.") }
                }
            }
            SurfacePanel {
                flat: true
                theme: page.theme; Layout.fillWidth: true; implicitHeight: tokenContent.implicitHeight + 28
                ColumnLayout {
                    id: tokenContent
                    anchors.fill: parent; anchors.margins: 14; spacing: 8
                    Label { text: "API Token"; font.weight: Font.DemiBold }
                    RowLayout {
                        Input {
                            id: tokenField; objectName: "modelToken"; enabled: page.editable
                            maximumLength: 4096; echoMode: page.showToken ? TextInput.Normal : TextInput.Password
                            inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                            placeholderText: page.provider.configured ? qsTranslate("Launcher", "Пустое поле — использовать настроенный ключ") : qsTranslate("Launcher", "Вставьте ключ выбранного провайдера")
                            onTextEdited: page.dirty = true
                        }
                        UiButton {
                            objectName: "revealModelToken"; theme: page.theme
                            text: page.showToken ? qsTranslate("Launcher", "Скрыть") : qsTranslate("Launcher", "Показать"); enabled: page.editable && tokenField.text.length > 0
                            onClicked: page.showToken = !page.showToken
                        }
                    }
                    Hint { text: qsTranslate("Launcher", "Ключи сохраняются на этом компьютере. Новый токен заменяет ключ выбранного провайдера.") }
                }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 10
        UiButton {
            objectName: "applyModel"; theme: page.theme; text: qsTranslate("Launcher", "Применить"); primary: true
            enabled: page.editable && page.validDraft
            onClicked: page.apply()
        }
        UiButton { objectName: "refreshModels"; theme: page.theme; text: qsTranslate("Launcher", "Обновить"); enabled: client.online && !client.modelsBusy; onClicked: client.refreshModels() }
        BusyIndicator { running: client.modelsBusy; visible: running; Layout.preferredWidth: 24; Layout.preferredHeight: 24; palette.highlight: page.theme.accent }
        Hint { text: client.modelsBusy ? qsTranslate("Launcher", "Подключение…") : page.dirty ? qsTranslate("Launcher", "Изменения не применены") : "" }
    }
}
