import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    required property QtObject theme
    required property var client
    signal chatRequested()
    signal petsRequested()
    property bool voiceRequestPending: false
    property bool requestedListening: false
    property bool monitorEnabled: true
    onMonitorEnabledChanged: watchInput()
    readonly property bool voiceReady: client.online && client.listeningReady
    readonly property bool voiceActive: voiceReady && client.listening
    readonly property var voiceInstall: client.voiceInstall || ({})
    readonly property var voicePreparation: client.voicePreparation || ({})
    readonly property var scottInfo: ((client.settings.voices || {}).voices || []).find(function(v) { return v.id === "scott-voice" }) || ({})
    readonly property bool voiceKnown: client.voiceInstallReady && (client.settingsReady || []).indexOf("voices") >= 0
    readonly property bool voiceMissing: voiceKnown && scottInfo.available === false
    readonly property bool needsVoiceInstall: voiceMissing && voiceInstall.supported === true
    readonly property bool installing: ["running", "cancelling"].indexOf(voiceInstall.state) >= 0
    readonly property bool warming: ["running", "cancelling"].indexOf(voicePreparation.state) >= 0
    function checkVoice() {
        if (!visible || !client.online) return
        if (!client.voiceInstallReady) client.refreshVoiceInstall()
        if (!client.voicePreparationReady) client.refreshVoicePreparation()
        if ((client.settingsReady || []).indexOf("voices") < 0 && !client.settingsBusy) client.refreshSettings()
    }
    function watchInput() { client.inputMonitoring = monitorEnabled && visible && client.online && client.listening }
    onVisibleChanged: { if (visible) checkVoice(); watchInput() }
    Component.onCompleted: { checkVoice(); watchInput() }
    onVoiceReadyChanged: if (!client.online) voiceRequestPending = false
    Connections {
        target: page.client
        function onStateChanged() { page.checkVoice(); page.watchInput() }
        function onListeningChanged() { page.watchInput(); if (!page.client.listeningBusy) page.voiceRequestPending = false }
    }
    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width, 830); height: parent.height
        spacing: 12
        Item { Layout.fillHeight: true; Layout.minimumHeight: 0 }
        ColumnLayout {
            Layout.fillWidth: true; spacing: page.height < 560 ? 8 : 14
            OverviewSignal {
                objectName: "overviewSignal"; theme: page.theme
                inputLevel: page.voiceActive ? (page.client.inputLevel || 0) : 0
                online: page.client.online; active: page.client.busy || page.voiceActive || page.client.starting
                animate: page.visible && page.theme.motion
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: Math.min(page.height * 0.25, 200)
                Layout.preferredHeight: Layout.preferredWidth
            }
            ColumnLayout {
                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: 14
                Text { Layout.alignment: Qt.AlignHCenter; text: qsTranslate("Launcher", "Скотт"); color: page.theme.ink; font.family: page.theme.fontFamily; font.pixelSize: page.height < 560 ? 30 : 38; font.weight: Font.DemiBold }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter; spacing: 8
                    Rectangle { width: 6; height: 6; radius: 3; color: page.client.online ? page.theme.success : page.theme.muted; opacity: page.client.busy || page.voiceActive ? 0.4 + assistantPulse.breath * 0.6 : 1 }
                    Text { text: page.client.busy ? qsTranslate("Launcher", "Работаю над задачей") : page.client.starting ? qsTranslate("Launcher", "Подключаюсь…") : !page.client.online ? qsTranslate("Launcher", "Ожидаю подключения") : page.client.listening ? qsTranslate("Launcher", "Голос включён") : qsTranslate("Launcher", "Готов помочь"); color: page.theme.muted; font.pixelSize: 13 }
                }
                Flow {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: Math.min(page.width, voiceButton.implicitWidth + chatButton.implicitWidth + petsButton.implicitWidth + 16)
                    Layout.topMargin: 6; spacing: 8
                    UiButton {
                        id: voiceButton
                        objectName: "overviewVoiceButton"
                        theme: page.theme; primary: true; implicitHeight: 40
                        text: page.installing ? qsTranslate("Launcher", "Отменить")
                            : page.needsVoiceInstall && !page.voiceActive ? qsTranslate("Launcher", "Установить Scott Voice")
                            : page.voiceRequestPending ? (page.requestedListening ? qsTranslate("Launcher", "Включаю микрофон…") : qsTranslate("Launcher", "Выключаю микрофон…")) : page.voiceActive ? qsTranslate("Launcher", "Остановить микрофон") : qsTranslate("Launcher", "Запустить Скотта")
                        enabled: page.client.online && (page.installing ? page.voiceInstall.state === "running" && !!page.voiceInstall.id
                            : page.voiceActive ? !page.client.listeningBusy
                            : page.needsVoiceInstall ? true
                            : page.voiceKnown && page.voiceReady && page.client.listeningAvailable && !page.client.listeningBusy && !page.client.settingsBusy)
                        onClicked: {
                            if (!enabled) return
                            if (page.installing) { page.client.cancelScottVoice(); return }
                            if (page.needsVoiceInstall && !page.voiceActive) { page.client.prepareScottVoice(false); return }
                            page.requestedListening = !page.client.listening
                            page.voiceRequestPending = true
                            page.client.setListening(page.requestedListening)
                        }
                    }
                    ChatToolButton { id: chatButton; objectName: "overviewChatButton"; theme: page.theme; text: qsTranslate("Launcher", "Диалог"); onClicked: page.chatRequested() }
                    ChatToolButton { id: petsButton; objectName: "overviewPetsButton"; theme: page.theme; text: qsTranslate("Launcher", "Питомцы"); onClicked: page.petsRequested() }
                }
                Text {
                    objectName: "overviewVoiceHint"; Layout.fillWidth: true
                    text: !page.client.online ? (page.client.starting ? qsTranslate("Launcher", "Скотт подключается…") : qsTranslate("Launcher", "Скотт не подключён. Проверьте запуск в настройках."))
                        : page.installing ? qsTranslate("Launcher", page.voiceInstall.message || "Подготовка Scott Voice")
                        : page.warming || page.voicePreparation.state === "failed" ? (page.voiceActive ? qsTranslate("Launcher", "Микрофон включён. Начните фразу со слова «Скотт».") + "\n" : "") + qsTranslate("Launcher", page.voicePreparation.message || "Загружаем модель и готовим голос…")
                        : page.voiceMissing ? (page.voiceInstall.supported === false
                            ? qsTranslate("Launcher", "Scott Voice здесь недоступен. Микрофон можно использовать для команд и ответов в чате.")
                            : qsTranslate("Launcher", page.scottInfo.reason || page.voiceInstall.message || "Scott Voice не установлен. Установите компонент в настройках голоса; чат доступен."))
                        : !page.voiceKnown || !page.client.listeningReady ? qsTranslate("Launcher", "Проверяю голосовой режим…")
                        : !page.client.listeningAvailable ? qsTranslate("Launcher", "Голосовой режим недоступен. Проверьте настройки звука.")
                        : page.voiceActive ? qsTranslate("Launcher", "Микрофон включён. Начните фразу со слова «Скотт».")
                        : qsTranslate("Launcher", "Включите микрофон и начните фразу со слова «Скотт».")
                    wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; color: page.theme.muted; font.pixelSize: 12
                }
                ProgressBar {
                    objectName: "overviewVoiceProgress"; Layout.fillWidth: true
                    visible: page.installing || page.warming
                    value: Number(page.voiceInstall.progress || 0)
                    indeterminate: page.warming || value === 0
                }
            }
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 0 }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 72; radius: page.theme.cardRadius
            color: "transparent"
            RowLayout {
                anchors.fill: parent; anchors.margins: 16; spacing: 16
                Repeater {
                    model: [{key:"cpu",name:qsTranslate("Launcher", "Процессор")},{key:"ram",name:qsTranslate("Launcher", "Память")},{key:"gpu",name:qsTranslate("Launcher", "Видеокарта")}]
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true; spacing: 5
                        Text { text: modelData.name; color: page.theme.muted; font.pixelSize: 11 }
                        Text { text: page.client.online && page.client.metrics[modelData.key] !== undefined ? Math.round(page.client.metrics[modelData.key]) + "%" : "—"; color: page.theme.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
                        Rectangle {
                            Layout.fillWidth: true; height: 2; radius: 1; color: page.theme.line
                            Rectangle {
                                width: parent.width * (page.client.online ? Math.max(0, Math.min(100, Number(page.client.metrics[modelData.key]) || 0)) : 0) / 100
                                height: 2; radius: 1; color: page.theme.accent
                                Behavior on width { enabled: page.visible && page.theme.motion; NumberAnimation { duration: 650; easing.type: Easing.OutCubic } }
                            }
                        }
                    }
                }
            }
        }
        UiNotice { objectName: "overviewError"; theme: page.theme; text: page.client.listeningError || page.client.error; error: true; Layout.fillWidth: true }
    }
    // The status pulse follows the same reduced-motion preference as the visual.
    Item { id: assistantPulse; property real breath: 0; visible: false
        SequentialAnimation on breath { running: page.visible && page.theme.motion && (page.client.busy || page.voiceActive); loops: Animation.Infinite; NumberAnimation { to: 1; duration: 700 } NumberAnimation { to: 0; duration: 700 } }
    }
}
