import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: page
    required property var client
    required property var avatar
    required property QtObject theme
    property bool dirty: false
    property bool syncing: false
    property string draftStyle: ""
    property var draftInterests: []
    property string localNotice: ""
    property alias nameDraft: nameField.text
    property alias aboutDraft: aboutField.text
    readonly property bool valid: nameField.text.length <= 60 && aboutField.text.length <= 300 && styleBox.currentIndex >= 0
    readonly property bool changed: dirty || avatar.dirty || interestField.text.trim().length > 0
    spacing: 10
    function syncDraft(force) {
        if (!force && (dirty || !client.profileReady)) return
        syncing = true
        nameField.text = client.profile.name || ""
        aboutField.text = client.profile.about || ""
        draftStyle = client.profile.style || ""
        draftInterests = (client.profile.interests || []).slice()
        syncing = false
    }
    function addInterest() {
        const value = interestField.text.trim()
        if (value.length === 0) return true
        if (draftInterests.indexOf(value) >= 0) { interestField.text = ""; return true }
        if (draftInterests.length >= 12 || value.length > 40) return false
        draftInterests = draftInterests.concat([value]); interestField.text = ""; dirty = true; localNotice = ""
        return true
    }
    function save() {
        if (!addInterest()) return
        localNotice = ""
        if (dirty) client.saveProfile(nameField.text, aboutField.text, draftStyle, draftInterests)
        else if (avatar.save()) localNotice = "Фото сохранено."
    }
    Component.onCompleted: syncDraft()
    Connections {
        target: page.client
        function onProfileChanged() { page.syncDraft() }
        function onProfileSaved() {
            page.dirty = false; page.syncDraft()
            page.avatar.save()
        }
    }
    component Label: Text { color: page.theme.ink; font.family: page.theme.fontFamily; font.pixelSize: 13; font.weight: Font.DemiBold }
    component Field: TextField {
        color: page.theme.ink; font.family: page.theme.fontFamily; placeholderTextColor: page.theme.muted
        selectionColor: page.theme.accent; selectedTextColor: page.theme.accentText
        implicitHeight: 40; leftPadding: 12; rightPadding: 12; selectByMouse: true; hoverEnabled: true
        enabled: !page.client.profileBusy
        background: FieldSurface { theme: page.theme; focused: parent.activeFocus; hovered: parent.hovered }
    }
    component Card: SurfacePanel {
        theme: page.theme; Layout.fillWidth: true
        default property alias content: body.data
        implicitHeight: body.implicitHeight + 32
        data: ColumnLayout { id: body; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 10 }
    }
    RowLayout {
        Text { text: page.changed ? "Изменения не сохранены" : client.profileBusy ? "Загрузка…" : ""; color: page.theme.muted; font.family: page.theme.fontFamily; font.pixelSize: 12; Layout.fillWidth: true }
        UiButton { theme: page.theme; text: "Обновить"; enabled: client.online && !client.profileBusy; onClicked: client.refreshProfile() }
    }
    UiNotice { theme: page.theme; text: client.profileError || avatar.error; error: true; Layout.fillWidth: true }
    UiNotice { theme: page.theme; text: !client.online ? "Scott недоступен. Изменения останутся в черновике." : ""; Layout.fillWidth: true }
    ScrollView {
        id: scroll
        objectName: "profileScroll"
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
        contentWidth: availableWidth; clip: true; rightPadding: 12
        ScrollBar.vertical: UiScrollBar { theme: page.theme; parent: scroll; x: scroll.width - width; height: scroll.availableHeight }
        ColumnLayout {
            width: scroll.availableWidth; spacing: 12
            Card {
                RowLayout {
                    spacing: 16; Layout.fillWidth: true
                    Rectangle {
                        width: 80; height: 80; radius: 40; color: page.theme.elevated
                        border.color: page.theme.line
                        Image { anchors.fill: parent; source: page.avatar.previewSource; cache: false; visible: page.avatar.hasAvatar }
                        NavIcon { anchors.centerIn: parent; width: 32; height: 32; symbol: 8; color: page.theme.muted; visible: !page.avatar.hasAvatar }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 8
                        Label { text: "Имя" }
                        Field {
                            id: nameField; objectName: "profileName"; Layout.fillWidth: true; maximumLength: 60
                            placeholderText: "Как к вам обращаться?"
                            onTextEdited: { page.dirty = true; page.localNotice = "" }
                        }
                        RowLayout {
                            UiButton { theme: page.theme; text: "Фото"; implicitHeight: 32; enabled: !client.profileBusy; onClicked: if (page.avatar.choose()) cropDialog.open() }
                            UiButton { theme: page.theme; text: "Кадр"; implicitHeight: 32; visible: page.avatar.hasAvatar; enabled: !client.profileBusy; onClicked: cropDialog.open() }
                            UiButton { theme: page.theme; text: "Удалить"; implicitHeight: 32; destructive: true; visible: page.avatar.hasAvatar; enabled: !client.profileBusy; onClicked: page.avatar.remove() }
                        }
                    }
                }
            }
            Card {
                RowLayout {
                    Label { text: "О себе"; Layout.fillWidth: true }
                    Text { text: aboutField.text.length + " / 300"; color: aboutField.text.length > 300 ? page.theme.danger : page.theme.muted; font.pixelSize: 12 }
                }
                TextArea {
                    id: aboutField; objectName: "profileAbout"
                    Layout.fillWidth: true; Layout.preferredHeight: Math.max(76, contentHeight + 24); padding: 12
                    enabled: !client.profileBusy; color: page.theme.ink; font.family: page.theme.fontFamily
                    placeholderText: "Что Scott стоит знать о вас?"; placeholderTextColor: page.theme.muted
                    wrapMode: TextEdit.Wrap; selectByMouse: true; textFormat: TextEdit.PlainText
                    selectionColor: page.theme.accent; selectedTextColor: page.theme.accentText
                    background: FieldSurface { theme: page.theme; focused: aboutField.activeFocus; hovered: false; invalid: aboutField.text.length > 300 }
                    onTextChanged: if (!page.syncing) { page.dirty = true; page.localNotice = "" }
                }
                RowLayout {
                    Label { text: "Характер ответов" }
                    UiComboBox {
                        id: styleBox; objectName: "profileStyle"
                        theme: page.theme; Layout.fillWidth: true; model: client.profile.styles || []
                        textRole: "title"; valueRole: "id"; enabled: client.profileReady && !client.profileBusy
                        currentIndex: { for (let i = 0; i < count; ++i) if (model[i].id === page.draftStyle) return i; return -1 }
                        onActivated: { page.draftStyle = currentValue; page.dirty = true; page.localNotice = "" }
                        ToolTip.visible: hovered; ToolTip.delay: 500
                        ToolTip.text: currentIndex >= 0 ? model[currentIndex].hint || "" : ""
                    }
                }
            }
            Card {
                RowLayout {
                    Label { text: "Интересы"; Layout.fillWidth: true }
                    Text { text: page.draftInterests.length + " / 12"; color: page.theme.muted; font.pixelSize: 12 }
                }
                Flow {
                    id: interestsFlow; Layout.fillWidth: true; spacing: 8
                    Repeater {
                        model: page.draftInterests
                        UiButton {
                            required property string modelData
                            theme: page.theme; text: modelData + "  ×"; implicitHeight: 32
                            width: Math.min(implicitWidth, interestsFlow.width)
                            Accessible.name: "Убрать интерес: " + modelData; enabled: !client.profileBusy
                            onClicked: { page.draftInterests = page.draftInterests.filter(function(v) { return v !== modelData }); page.dirty = true; page.localNotice = "" }
                        }
                    }
                }
                RowLayout {
                    Field {
                        id: interestField; objectName: "profileInterest"
                        Layout.fillWidth: true; maximumLength: 40; placeholderText: "Новый интерес"
                        onAccepted: page.addInterest()
                    }
                    UiButton { theme: page.theme; text: "Добавить"; enabled: !client.profileBusy && interestField.text.trim().length > 0 && page.draftInterests.length < 12; onClicked: page.addInterest() }
                }
            }
        }
    }
    RowLayout {
        UiButton {
            theme: page.theme; text: "Сохранить"; primary: true; objectName: "saveProfile"
            enabled: page.changed && !client.profileBusy && (interestField.text.trim().length === 0 || page.draftInterests.indexOf(interestField.text.trim()) >= 0 || page.draftInterests.length < 12)
                && (page.dirty || interestField.text.trim().length > 0 ? client.online && client.profileReady && page.valid : true)
            onClicked: page.save()
        }
        UiButton { theme: page.theme; text: "Отменить"; enabled: page.changed && !client.profileBusy; onClicked: { page.dirty = false; page.syncDraft(true); interestField.text = ""; page.avatar.revert(); page.localNotice = "" } }
        Text { text: page.changed ? "" : page.localNotice || client.profileNotice; color: page.theme.success; font.family: page.theme.fontFamily; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
    }
    Dialog {
        id: cropDialog; objectName: "avatarCropDialog"
        parent: Overlay.overlay; anchors.centerIn: parent; modal: true; padding: 18
        width: Math.min(420, parent.width - 32); title: "Кадрирование"; closePolicy: Popup.CloseOnEscape
        background: SurfacePanel { theme: page.theme; color: page.theme.popup }
        header: Text { text: cropDialog.title; color: page.theme.ink; font.family: page.theme.fontFamily; font.pixelSize: 15; font.weight: Font.DemiBold; leftPadding: 18; topPadding: 16; bottomPadding: 6 }
        onRejected: page.avatar.revert()
        contentItem: ColumnLayout {
            spacing: 12
            Item {
                Layout.alignment: Qt.AlignHCenter; implicitWidth: 220; implicitHeight: 220
                Image { anchors.fill: parent; source: page.avatar.previewSource; cache: false }
                DragHandler {
                    id: cropDrag; target: null
                    property real startX: 0; property real startY: 0
                    onActiveChanged: if (active) { startX = page.avatar.crop.x; startY = page.avatar.crop.y }
                    onActiveTranslationChanged: if (active) page.avatar.setCrop(page.avatar.crop.zoom, startX + activeTranslation.x, startY + activeTranslation.y)
                }
                HoverHandler { cursorShape: Qt.SizeAllCursor }
                WheelHandler {
                    acceptedModifiers: Qt.ControlModifier
                    onWheel: function(event) { page.avatar.setCrop(page.avatar.crop.zoom + event.angleDelta.y / 120 * 0.1, page.avatar.crop.x, page.avatar.crop.y) }
                }
            }
            RowLayout {
                UiSlider { theme: page.theme; Layout.fillWidth: true; from: 1; to: 4; stepSize: 0.05; value: page.avatar.crop.zoom; Accessible.name: "Приближение фото"; onMoved: page.avatar.setCrop(value, page.avatar.crop.x, page.avatar.crop.y) }
                Text { text: page.avatar.crop.zoom.toFixed(1) + "×"; color: page.theme.ink; font.pixelSize: 12 }
            }
            RowLayout {
                UiButton { theme: page.theme; text: "Сбросить"; onClicked: page.avatar.resetCrop() }
                Item { Layout.fillWidth: true }
                UiButton { theme: page.theme; text: "Готово"; primary: true; onClicked: cropDialog.close() }
            }
        }
    }
}
