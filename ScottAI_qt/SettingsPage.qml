import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: page
    readonly property var voiceInstall: client.voiceInstall || ({})
    readonly property var voicePreparation: client.voicePreparation || ({})
    readonly property bool voiceWarming: ["running", "cancelling"].indexOf(voicePreparation.state) >= 0
    readonly property bool voicePreparing: ["running", "cancelling"].indexOf(voiceInstall.state) >= 0
    required property var client
    required property QtObject theme
    required property bool backgroundAllowed
    required property bool backgroundEnabled
    property bool notificationsEnabled: true
    signal notificationsChanged(bool enabled)
    signal backgroundChanged(bool enabled)
    signal resetAppearanceRequested()
    property int section: 0
    property int displayedSection: 0
    property int sectionDirection: 1
    property bool sectionReady: false
    readonly property bool sectionTransitioning: sectionOut.running || sectionIn.running
    property real volumeDraft: 100
    property bool volumeDirty: false
    readonly property var audio: client.settings.audio || ({})
    readonly property var audioState: audio.settings || ({})
    readonly property var device: client.settings.device || ({})
    readonly property var voices: client.settings.voices || ({})
    readonly property var characters: client.settings.characters || ({})
    readonly property bool scottSelected: voices.current === "scott-voice"
    readonly property var scottInfo: (voices.voices || []).find(function(v) { return v.id === "scott-voice" }) || ({})
    function editable(group) { return client.online && !client.settingsBusy && client.settingsReady.indexOf(group) >= 0 }
    function indexOf(model, value) {
        for (let i = 0; i < model.length; ++i) if (model[i].id === value) return i
        return -1
    }
    function deviceList(kind) {
        const devices = audio.devices || ({})
        const list = [{id: "", title: "Как в системе"}]
        for (const entry of (devices[kind] || [])) list.push({id: entry.name, title: entry.name + (entry.default ? " · по умолчанию" : "")})
        return list
    }
    function syncVolume() {
        const saved = audioState.volume
        if (saved !== undefined && (!volumeDirty || Math.round(volumeDraft) === saved)) { volumeDraft = saved; volumeDirty = false }
    }
    function commitSection() { displayedSection = section }
    function settleSection() {
        sectionOut.stop(); sectionIn.stop()
        commitSection()
        sections.opacity = 1; sections.sectionOffset = 0
    }
    function changeSection() {
        if (!sectionReady) return
        if (!theme.motion || !visible) { settleSection(); return }
        if (sectionOut.running) return
        if (section === displayedSection && !sectionIn.running) return
        sectionDirection = section >= displayedSection ? 1 : -1
        sectionIn.stop(); sectionOut.start()
    }
    Component.onCompleted: { sectionReady = true; syncVolume(); settleSection() }
    onSectionChanged: changeSection()
    onVisibleChanged: if (sectionReady && !visible) settleSection()
    Connections { target: page.client; function onSettingsChanged() { page.syncVolume() } }
    Connections { target: page.theme; function onMotionChanged() { if (!page.theme.motion && page.sectionReady) page.settleSection() } }
    spacing: 14

    component Heading: Text { color: page.theme.ink; font.family: page.theme.fontFamily; font.pixelSize: 15; font.weight: Font.DemiBold }
    component Hint: Text { color: page.theme.muted; font.family: page.theme.fontFamily; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
    component SettingCard: SurfacePanel {
        theme: page.theme
        default property alias content: body.data
        implicitHeight: body.implicitHeight + 32
        Layout.fillWidth: true
        data: ColumnLayout {
            id: body
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: 16; spacing: 10
        }
    }
    component Option: UiComboBox { theme: page.theme; textRole: "title"; valueRole: "id"; Layout.fillWidth: true }
    component SectionScroll: ScrollView {
        id: view
        clip: true; contentWidth: availableWidth; rightPadding: 12
        ScrollBar.vertical: UiScrollBar { theme: page.theme; parent: view; x: view.width - width; y: view.topPadding; height: view.availableHeight }
    }
    RowLayout {
        Layout.fillWidth: true; spacing: 8
        UiSegmentedControl {
            objectName: "settingsTabs"
            theme: page.theme
            model: ["Голос", "Обработка", "Прочее"]
            currentIndex: page.section
            onActivated: function(index) { page.section = index }
        }
        Item { Layout.fillWidth: true }
        UiButton { theme: page.theme; text: client.settingsBusy ? "Загрузка…" : "Обновить"; enabled: client.online && !client.settingsBusy; onClicked: client.refreshSettings() }
    }
    UiNotice {
        theme: page.theme; Layout.fillWidth: true
        error: !client.online || client.settingsError.length > 0
        text: !client.online ? "Подключите Scott, чтобы загрузить и изменить настройки." : client.settingsError.length > 0 ? client.settingsError : client.settingsNotice
    }
    Item {
        id: activity
        objectName: "settingsActivity"
        Layout.fillWidth: true
        property real reveal: page.client.online && page.client.settingsBusy ? 1 : 0
        implicitHeight: 32 * reveal
        opacity: reveal; visible: reveal > 0; clip: true
        Behavior on reveal { enabled: page.theme.motion; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Row {
            spacing: 10
            Item {
                id: spinner
                width: 20; height: 20
                Repeater {
                    model: 8
                    Rectangle {
                        required property int index
                        x: 8 + Math.cos(index * Math.PI / 4) * 7
                        y: 8 + Math.sin(index * Math.PI / 4) * 7
                        width: 4; height: 4; radius: 2
                        color: page.theme.accent; opacity: (index + 1) / 8
                    }
                }
                RotationAnimator on rotation {
                    from: 0; to: 360; duration: 1000; loops: Animation.Infinite
                    running: page.client.settingsBusy && page.visible && page.theme.motion
                }
            }
            Text {
                text: "Scott обрабатывает запрос…"; color: page.theme.muted
                font.family: page.theme.fontFamily; font.pixelSize: 12
                height: 20; verticalAlignment: Text.AlignVCenter
            }
        }
    }
    Item {
        objectName: "settingsScroll"
        readonly property var contentItem: page.displayedSection === 0 ? voiceScroll.contentItem : page.displayedSection === 1 ? processingScroll.contentItem : otherScroll.contentItem
        Layout.fillWidth: true; Layout.fillHeight: true
        clip: true
        StackLayout {
            id: sections
            objectName: "settingsSections"
            anchors.fill: parent
            currentIndex: page.displayedSection
            property real sectionOffset: 0
            transform: Translate { x: sections.sectionOffset }
            enabled: page.displayedSection === page.section && !sectionOut.running
            SectionScroll {
                id: voiceScroll
                ColumnLayout {
                    width: voiceScroll.availableWidth; spacing: 16
                    SettingCard {
                        Heading { text: "Громкость и тихий режим" }
                        UiSwitch {
                            objectName: "quietSwitch"
                            theme: page.theme; text: "Scott выполняет команды без озвучивания"
                            Layout.fillWidth: true
                            checked: page.audioState.quiet || false; enabled: page.editable("audio")
                            onToggled: client.applySetting("quiet", {quiet: checked})
                        }
                        Hint { text: "Тихий режим останавливает текущую речь. Пробная фраза звучит и в этом режиме." }
                        RowLayout {
                            UiSlider {
                                objectName: "speechVolume"
                                theme: page.theme; Layout.fillWidth: true; value: page.volumeDraft
                                enabled: page.editable("audio")
                                Accessible.name: "Громкость речи"
                                onMoved: { page.volumeDraft = value; page.volumeDirty = true }
                            }
                            Text { text: Math.round(page.volumeDraft) + "%"; color: page.theme.ink; font.family: page.theme.fontFamily; Layout.preferredWidth: 50 }
                            UiButton {
                                objectName: "saveVolume"
                                theme: page.theme; text: "Применить"; enabled: page.editable("audio") && page.volumeDirty
                                onClicked: client.applySetting("audio", {volume: Math.round(page.volumeDraft)})
                            }
                        }
                    }
                    SettingCard {
                        Heading { text: "Звуковые устройства" }
                        Hint { text: page.audio.available === false ? "Звуковая подсистема недоступна." : "Устройства сохраняются по названию. «Как в системе» возвращает автоматический выбор." }
                        Hint { text: "Динамики или наушники" }
                        Option {
                            objectName: "outputDevice"
                            model: page.deviceList("output"); currentIndex: Math.max(0, page.indexOf(model, page.audioState.output_device || ""))
                            enabled: page.editable("audio") && page.audio.available === true
                            onActivated: client.applySetting("audio", {output_device: currentValue})
                        }
                        Hint { text: "Микрофон" }
                        Option {
                            objectName: "inputDevice"
                            model: page.deviceList("input"); currentIndex: Math.max(0, page.indexOf(model, page.audioState.input_device || ""))
                            enabled: page.editable("audio") && page.audio.available === true
                            onActivated: client.applySetting("audio", {input_device: currentValue})
                        }
                    }
                    SettingCard {
                        objectName: "voiceCard"
                        Heading { text: "Голос Scott" }
                        Hint {
                            objectName: "voiceInstallMessage"
                            text: page.voiceInstall.message || (page.voiceInstall.installed ? "Scott Voice установлен. Можно проверить его готовность." : "Scott Voice можно установить отдельно. Потребуются интернет и несколько гигабайт на диске. Пока проверена NVIDIA/CUDA.")
                        }
                        ProgressBar {
                            objectName: "voiceInstallProgress"
                            Layout.fillWidth: true
                            visible: page.voicePreparing
                            indeterminate: true
                            Accessible.name: "Подготовка Scott Voice"
                            background: Rectangle { implicitHeight: 4; radius: 2; color: page.theme.line }
                            contentItem: Item {
                                implicitHeight: 4; clip: true
                                Rectangle {
                                    width: parent.width * 0.3; height: 4; radius: 2; color: page.theme.accent
                                    SequentialAnimation on x {
                                        running: page.voicePreparing && page.visible && page.theme.motion
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 0; to: Math.max(0, voiceInstallProgress.width * 0.7); duration: 950; easing.type: Easing.InOutSine }
                                        NumberAnimation { from: Math.max(0, voiceInstallProgress.width * 0.7); to: 0; duration: 950; easing.type: Easing.InOutSine }
                                    }
                                }
                            }
                            id: voiceInstallProgress
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            UiButton {
                                objectName: "installScottVoice"
                                theme: page.theme
                                text: page.scottInfo.error === "runtime_update_required" ? "Обновить Scott Voice" : page.voiceInstall.state === "failed" || page.voiceInstall.state === "cancelled" ? "Повторить установку" : "Установить Scott Voice"
                                visible: !page.voiceInstall.installed || page.voiceInstall.state === "failed" || page.voiceInstall.state === "cancelled" || page.scottInfo.error === "runtime_update_required"
                                enabled: client.online && client.voiceInstallReady && page.voiceInstall.supported === true && !page.voicePreparing
                                onClicked: client.prepareScottVoice(false)
                            }
                            UiButton {
                                objectName: "checkScottVoice"
                                theme: page.theme; text: "Проверить"
                                enabled: client.online && client.voiceInstallReady && !page.voicePreparing
                                onClicked: client.prepareScottVoice(true)
                            }
                            UiButton {
                                objectName: "cancelScottVoice"
                                theme: page.theme; text: page.voiceInstall.state === "cancelling" ? "Отмена…" : "Отменить"
                                visible: page.voicePreparing
                                enabled: client.online && page.voiceInstall.state === "running" && !!page.voiceInstall.id
                                onClicked: client.cancelScottVoice()
                            }
                        }
                        Hint { text: "Локальные голоса работают без интернета. Scott Voice — собственный мужской тембр. Выбор сохраняется." }
                        RowLayout {
                            Option {
                                objectName: "voiceChoice"
                                model: (page.voices.voices || []).map(function(v) { return {id:v.id, title:v.label + (v.available === false ? " · недоступен" : v.local ? " · локальный" : " · облачный")} })
                                currentIndex: page.indexOf(model, page.voices.current)
                                enabled: page.editable("voices") && count > 0
                                onActivated: client.applySetting("voice", {voice: currentValue})
                            }
                            UiButton { theme: page.theme; text: "Прослушать"; enabled: page.editable("voices"); onClicked: client.previewVoice() }
                        }
                        Hint { visible: page.scottSelected || page.scottInfo.available === false; text: page.scottInfo.reason || "Scott Voice работает локально. Подготовка новой фразы занимает несколько секунд; готовые ответы берутся из кеша." }
                        Hint { text: page.scottSelected ? "Характер Scott Voice" : "Характер звучания" }
                        Option {
                            objectName: "voiceCharacter"
                            model: page.scottSelected ? (page.voices.scott_profiles || []) : (page.characters.characters || [])
                            currentIndex: page.indexOf(model, page.scottSelected ? page.voices.scott_profile : page.characters.current)
                            enabled: page.editable(page.scottSelected ? "voices" : "characters") && count > 0 && (!page.scottSelected || page.scottInfo.available === true)
                            onActivated: page.scottSelected ? client.applySetting("voiceProfile", {voice:"scott-voice", profile:currentValue}) : client.applySetting("audio", {character: currentValue})
                        }
                        Hint { text: page.scottSelected ? "Оцените цифровую окраску кнопкой «Прослушать». При сбое Scott использует резервный голос." : "«Спокойный» смягчает резкие звуки, сохраняя высоту и темп. Оцените кнопкой «Прослушать»." }
                        Hint {
                            objectName: "voicePreparationMessage"
                            visible: page.scottSelected
                            text: page.voicePreparation.message || "Подготовьте модель перед разговором, чтобы сократить ожидание первого ответа. После двух минут простоя она освобождает память."
                        }
                        RowLayout {
                            visible: page.scottSelected
                            UiButton {
                                objectName: "warmScottVoice"
                                theme: page.theme; text: "Подготовить к речи"
                                visible: !page.voiceWarming && page.voicePreparation.model_loaded !== true
                                enabled: page.editable("voices") && client.voicePreparationReady && page.scottInfo.available === true
                                onClicked: client.warmScottVoice()
                            }
                            UiButton {
                                objectName: "releaseScottVoice"
                                theme: page.theme
                                text: page.voiceWarming ? "Отменить подготовку" : "Освободить модель"
                                visible: page.voiceWarming || page.voicePreparation.model_loaded === true
                                enabled: client.online && client.voicePreparationReady && page.voicePreparation.state !== "cancelling" && !!page.voicePreparation.id
                                onClicked: client.releaseScottVoice()
                            }
                        }
                        UiSwitch {
                            objectName: "scottStreaming"
                            theme: page.theme; text: "Раннее начало речи"
                            Layout.fillWidth: true
                            visible: page.scottSelected
                            checked: page.voices.scott_streaming === true
                            enabled: page.editable("voices") && page.scottInfo.streaming_available === true
                            onToggled: client.applySetting("voiceStreaming", {voice:"scott-voice", streaming:checked})
                        }
                        Hint {
                            visible: page.scottSelected
                            text: "Эксперимент: Scott начинает говорить во время подготовки ответа. Между фрагментами возможны паузы."
                        }
                        Hint { visible: page.scottSelected && page.voices.scott_streaming === true; text: "Запас звука" }
                        Option {
                            objectName: "scottBuffer"
                            visible: page.scottSelected && page.voices.scott_streaming === true
                            model: page.voices.scott_buffers || []
                            currentIndex: page.indexOf(model, page.voices.scott_buffer || "immediate")
                            enabled: page.editable("voices") && page.scottInfo.available === true && count > 0
                            onActivated: client.applySetting("voiceBuffer", {voice:"scott-voice", buffer:currentValue})
                        }
                        Hint {
                            visible: page.scottSelected && page.voices.scott_streaming === true
                            text: "Больше запаса — позже начало, меньше ожидания блоков. «Вся фраза» готовит её целиком перед воспроизведением."
                        }
                        UiSwitch {
                            objectName: "scottAcceleration"
                            theme: page.theme; text: "Ускоренный синтез"
                            Layout.fillWidth: true
                            visible: page.scottSelected
                            checked: page.voices.scott_acceleration === true
                            enabled: page.editable("voices") && (page.scottInfo.acceleration_available === true || checked)
                            onToggled: client.applySetting("voiceAcceleration", {voice:"scott-voice", acceleration:checked})
                        }
                        Hint {
                            visible: page.scottSelected
                            text: "Эксперимент: ускорение может изменить тембр и паузы. Сравните звучание кнопкой «Прослушать»."
                        }
                    }
                }
            }
            SectionScroll {
                id: processingScroll
                ColumnLayout {
                    width: processingScroll.availableWidth; spacing: 16
                    Repeater {
                        model: [{id:"whisper", title:"Распознавание речи"}, {id:"silero", title:"Синтез речи"}]
                        SettingCard {
                            id: engineCard
                            required property var modelData
                            readonly property var info: (page.device.engines || ({}))[modelData.id] || ({})
                            Heading { text: engineCard.modelData.title }
                            Hint { text: "Выбрано: " + (engineCard.info.device_label || (engineCard.info.device === "cuda" ? "видеокарта" : engineCard.info.device === "cpu" ? "процессор" : engineCard.info.device || "—")) }
                            RowLayout {
                                Repeater {
                                    model: engineCard.info.options || [{id:"auto", title:"Авто", available:true}, {id:"cuda", title:"NVIDIA", available:!!page.device.cuda_available}, {id:"rocm", title:"AMD", available:!!page.device.rocm_available}, {id:"cpu", title:"Процессор", available:true}]
                                    UiButton {
                                        required property var modelData
                                        theme: page.theme; text: modelData.title; primary: engineCard.info.choice === modelData.id
                                        enabled: page.editable("device") && !engineCard.info.locked_by_env && !!modelData.available
                                        onClicked: client.applySetting("device", {engine:engineCard.modelData.id, choice:modelData.id})
                                    }
                                }
                            }
                            Hint { text: engineCard.info.locked_by_env ? "Выбор задан переменной " + engineCard.info.env_var + ". Измените её, чтобы переключать устройство здесь." : "Авто выбирает доступное устройство. Модель перезагрузится при следующем обращении." }
                        }
                    }
                }
            }
            SectionScroll {
                id: otherScroll
                ColumnLayout {
                    width: otherScroll.availableWidth; spacing: 16
                    SettingCard {
                        Heading { text: "Работа в фоне" }
                        UiSwitch {
                            theme: page.theme; text: "Закрывать в трей"
                            Layout.fillWidth: true
                            checked: page.backgroundEnabled; enabled: page.backgroundAllowed
                            onToggled: page.backgroundChanged(checked)
                        }
                        UiSwitch {
                            theme: page.theme; text: "Уведомлять о готовом ответе"
                            Layout.fillWidth: true; checked: page.notificationsEnabled; enabled: page.backgroundAllowed
                            onToggled: page.notificationsChanged(checked)
                        }
                    }
                    SettingCard {
                        Heading { text: "Оформление лаунчера" }
                        Hint { text: "Вернуть тему, стиль, значок, прозрачность и анимации к исходным значениям." }
                        UiButton { theme: page.theme; text: "Сбросить оформление"; destructive: true; onClicked: resetDialog.open() }
                    }
                    SettingCard {
                        Heading { text: "Версии сохранённых действий" }
                        Repeater {
                            model: (client.settings.versions || ({})).data || []
                            Hint { required property var modelData; text: modelData.item_id + " · " + modelData.item_type + " · версий: " + modelData.versions_count }
                        }
                        Hint { visible: !client.settings.versions || (client.settings.versions.data || []).length === 0; text: "Версии появятся после создания или изменения действия." }
                    }
                }
            }
        }
    }
    SequentialAnimation {
        id: sectionOut
        ParallelAnimation {
            NumberAnimation { target: sections; property: "opacity"; to: 0; duration: 70; easing.type: Easing.InQuad }
            NumberAnimation { target: sections; property: "sectionOffset"; to: -8 * page.sectionDirection; duration: 70; easing.type: Easing.InQuad }
        }
        ScriptAction {
            script: {
                page.commitSection()
                sections.sectionOffset = 12 * page.sectionDirection
                sectionIn.start()
            }
        }
    }
    ParallelAnimation {
        id: sectionIn
        NumberAnimation { target: sections; property: "opacity"; to: 1; duration: 200; easing.type: Easing.OutCubic }
        NumberAnimation { target: sections; property: "sectionOffset"; to: 0; duration: 220; easing.type: Easing.OutCubic }
    }
    Dialog {
        id: resetDialog
        objectName: "resetAppearanceDialog"
        parent: Overlay.overlay; anchors.centerIn: parent; modal: true; padding: 24
        width: Math.min(460, parent.width - 64)
        background: SurfacePanel { theme: page.theme; color: page.theme.popup }
        contentItem: ColumnLayout {
            spacing: 18
            Heading { text: "Сбросить оформление?" }
            Hint { text: "Тема, стиль, прозрачность, значок и анимации Qt-лаунчера вернутся к исходным значениям." }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                UiButton { theme: page.theme; text: "Отмена"; onClicked: resetDialog.close() }
                UiButton { theme: page.theme; text: "Сбросить"; destructive: true; onClicked: { page.resetAppearanceRequested(); resetDialog.close() } }
            }
        }
    }
}
