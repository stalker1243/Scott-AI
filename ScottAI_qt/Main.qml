import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import QtQuick.Window
import "StyleCatalog.js" as Styles
import "CapabilityInfo.js" as CapabilityInfo

ApplicationWindow {
    id: root
    width: 920; height: 660
    minimumWidth: 800; minimumHeight: 560
    // Prepare the selected page and native material before the first reveal.
    visible: false
    opacity: revealProgress
    title: "ScottAI"
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinMaxButtonsHint | (alwaysOnTop ? Qt.WindowStaysOnTopHint : 0)
    font.family: visual.fontFamily
    font.pixelSize: 14
    property bool navigationExpanded: preferences.initial.navigationExpanded
    property bool alwaysOnTop: preferences.initial.alwaysOnTop
    property bool trayNotifications: preferences.initial.trayNotifications
    property real navigationWidth: navigationExpanded ? 164 : 64
    property real moveEmphasis: windowEffects.interacting ? 1 : 0
    property string chatWarningFeature: ""
    readonly property string chatCapabilityWarning: chatWarningFeature.length ? CapabilityInfo.reason(backend.chatCapabilities, chatWarningFeature) : ""
    function requestChatFeature(feature) {
        const supported = CapabilityInfo.reason(backend.chatCapabilities, feature).length === 0
        chatWarningFeature = supported ? "" : feature
        return supported
    }
    property real revealProgress: animationsEnabled ? 0 : 1
    property string dismissAction: ""
    readonly property bool pendingHide: dismissAction === "hide"
    readonly property bool pendingMinimize: dismissAction === "minimize"
    readonly property bool pendingQuit: dismissAction === "close" || dismissAction === "quit"
    readonly property bool geometryAnimating: windowMotion.running
    readonly property int presentationVisibility: geometryAnimating ? windowMotion.targetVisibility : visibility
    property int previousVisibility: Window.Hidden
    property bool closeApproved: false
    Behavior on navigationWidth { enabled: visual.motion; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    Behavior on moveEmphasis { enabled: visual.motion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    property int selectedTab: 0
    property int displayedTab: 0
    property int transitionDirection: 1
    property bool sceneReady: false
    property bool darkMode: preferences.initial.dark
    property string accentOverride: preferences.initial.accentOverride
    property color accentColor: accentOverride.length > 0 ? accentOverride : stylePalette.accent
    property bool lightIcon: preferences.initial.lightIcon
    property bool hideToTray: preferences.initial.hideToTray
    property bool animationsEnabled: preferences.initial.animations
    property string styleId: Styles.resolve(preferences.initial.styleId).id
    property int glassFrost: preferences.initial.glassFrost
    readonly property bool glassActive: styleDefinition.decoration === "glass"
    // Windows supplies the backdrop blur. This veil controls the material's density.
    readonly property real glassOpacity: glassActive ? 0.16 + 0.64 * glassFrost / 100 : 1
    readonly property var styleDefinition: Styles.resolve(styleId)
    readonly property var stylePalette: Styles.palette(styleDefinition, darkMode)
    property var transparencyByStyle: preferences.initial.transparencyByStyle
    property color baseSurface: stylePalette.surface
    readonly property int panelTransparency: transparencyByStyle[styleDefinition.id] !== undefined
        ? Math.max(0, Math.min(100, transparencyByStyle[styleDefinition.id])) : Math.round((1 - baseSurface.a) * 100)
    function setPanelTransparency(value) {
        const values = Object.assign({}, transparencyByStyle)
        values[styleDefinition.id] = Math.max(0, Math.min(100, Math.round(value)))
        transparencyByStyle = values
    }
    function resetAppearance() {
        darkMode = true; styleId = "classic"; accentOverride = ""; lightIcon = false
        animationsEnabled = true; transparencyByStyle = {}; glassFrost = 40; persist()
    }
    QtObject {
        id: visual
        property bool motion: root.animationsEnabled && root.visible && root.visibility !== Window.Minimized
        property color bg: root.bg
        property color surface: root.surface
        property color elevated: root.elevated
        property color ink: root.ink
        property color muted: root.muted
        property color line: root.line
        property color accent: root.accentColor
        property color popup: root.stylePalette.popup
        property color accentText: Styles.accentText(root.accentColor)
        property string decoration: root.styleDefinition.decoration
        property string fontFamily: root.styleDefinition.fontFamily
        property bool dark: root.darkMode
        property int panelTransparency: root.panelTransparency
        property real glassOpacity: root.glassOpacity
        property color danger: root.darkMode ? "#efa28d" : "#a33f2e"
        property color success: root.darkMode ? "#53cf9e" : "#167651"
        property real cardRadius: root.styleDefinition.cardRadius
        property real controlRadius: root.styleDefinition.controlRadius
    }
    property color bg: stylePalette.bg
    property color sidebar: Qt.alpha(stylePalette.sidebar, (1 - panelTransparency / 100) * glassOpacity)
    property color surface: Qt.alpha(baseSurface, (1 - panelTransparency / 100) * glassOpacity)
    property color elevated: glassActive ? Qt.alpha(stylePalette.elevated, Math.max(0.4, glassOpacity)) : stylePalette.elevated
    property color ink: stylePalette.ink
    property color muted: stylePalette.muted
    property color line: stylePalette.line
    readonly property var tabs: ["Обзор", "Диалог", "Система", "Внешний вид", "Память", "Настройки", "Профиль", "Действия", "Протоколы", "Модели"]

    color: "transparent"
    background: Rectangle {
        objectName: "windowSurface"
        radius: root.presentationVisibility === Window.Maximized || root.presentationVisibility === Window.FullScreen ? 0 : Math.min(16, root.styleDefinition.cardRadius)
        color: root.glassActive ? Qt.alpha(root.bg, root.glassOpacity) : root.bg
        border.color: root.moveEmphasis > 0.01 ? Qt.alpha(root.accentColor, 0.35 + root.moveEmphasis * 0.45) : root.line
        StyleBackdrop { anchors.fill: parent; anchors.margins: 1; theme: visual }
        Behavior on color { enabled: visual.motion; ColorAnimation { duration: 180 } }
        Behavior on radius { enabled: visual.motion; NumberAnimation { duration: 340; easing.type: Easing.InOutCubic } }
    }
    header: WindowTitleBar {
        windowHost: root; theme: visual
        pageTitle: root.tabs[root.displayedTab]; navigationExpanded: root.navigationExpanded
        statusText: backend.status; online: backend.online
        onToggleNavigation: { root.navigationExpanded = !root.navigationExpanded; root.persistWorkspace() }
        logoSource: root.lightIcon ? "qrc:/brand/scott-logo-light.png" : "qrc:/brand/scott-logo.png"
    }
    WindowResizeHandles { parent: Overlay.overlay; anchors.fill: parent; z: 100; windowHost: root }
    Behavior on bg { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
    Behavior on sidebar { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
    Behavior on surface { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
    Behavior on elevated { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
    Behavior on ink { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
    Behavior on muted { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
    Behavior on line { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
    function persist() { preferences.save(darkMode, accentOverride, lightIcon, hideToTray, animationsEnabled, styleDefinition.id, transparencyByStyle, glassFrost) }
    function persistWorkspace() { preferences.saveWorkspace(navigationExpanded, alwaysOnTop, trayNotifications) }
    function restoreFromTray() {
        if (pendingQuit) return
        dismissAction = ""; hideAnimation.stop(); revealAnimation.stop()
        if (!visible || visibility === Window.Minimized) revealProgress = animationsEnabled ? 0 : 1
        show(); raise(); requestActivate()
        // The tray controller restores the previous maximized state first.
        Qt.callLater(function() {
            if (root.dismissAction.length || !root.visible) return
            if (visual.motion) revealAnimation.start()
            else root.revealProgress = 1
        })
        if (selectedTab === 1) Qt.callLater(function() { composer.forceActiveFocus() })
    }
    function hideToBackground() {
        dismissWindow("hide")
    }
    function requestQuit() {
        dismissWindow("quit")
    }
    function minimizeAnimated() {
        if (!pendingQuit && visibility !== Window.Minimized) dismissWindow("minimize")
    }
    function prepareWindowMotion() {
        if (pendingQuit) return false
        if (dismissAction.length) restoreFromTray()
        dockAnimation.stop()
        return true
    }
    function maximizeAnimated() {
        if (prepareWindowMotion()) windowMotion.maximize()
    }
    function restoreSizeAnimated() {
        if (prepareWindowMotion()) windowMotion.restore()
    }
    function toggleMaximizedAnimated() {
        if (prepareWindowMotion()) windowMotion.toggleMaximized()
    }
    function toggleFullScreenAnimated() {
        if (prepareWindowMotion()) windowMotion.toggleFullScreen()
    }
    Shortcut { sequence: "F11"; onActivated: root.toggleFullScreenAnimated() }
    Shortcut {
        sequence: "Esc"; enabled: root.presentationVisibility === Window.FullScreen
        onActivated: windowMotion.leaveFullScreen()
    }
    function dismissWindow(action) {
        if (dismissAction === "quit" || (pendingQuit && action !== "quit")) return
        windowMotion.finish()
        dismissAction = action
        revealAnimation.stop(); dockAnimation.stop()
        if (!visual.motion) finishDismiss()
        else if (!hideAnimation.running) hideAnimation.start()
    }
    function finishDismiss() {
        const action = dismissAction
        dismissAction = ""
        if (action === "hide") hide()
        else if (action === "minimize") showMinimized()
        else if (action === "close" || action === "quit") {
            closeApproved = true
            close()
            closeApproved = false
        }
        revealProgress = 1
        if (action === "quit") Qt.quit()
    }
    function moveToPosition(nextX, nextY) {
        dockAnimation.stop()
        if (visual.motion) { dockX.to = nextX; dockY.to = nextY; dockAnimation.start() }
        else { x = nextX; y = nextY }
    }
    function snapToScreenEdge() {
        if (!visible || visibility !== Window.Windowed) return
        const area = windowEffects.workArea
        if (area.width <= 0 || area.height <= 0) return
        let nextX = x, nextY = y
        if (Math.abs(x - area.x) < 24) nextX = area.x + 8
        else if (Math.abs(x + width - area.x - area.width) < 24) nextX = area.x + area.width - width - 8
        if (Math.abs(y - area.y) < 24) nextY = area.y + 8
        else if (Math.abs(y + height - area.y - area.height) < 24) nextY = area.y + area.height - height - 8
        if (nextX !== x || nextY !== y) moveToPosition(nextX, nextY)
    }
    function centerOnScreen() {
        if (visibility !== Window.Windowed) showNormal()
        const area = windowEffects.workArea
        moveToPosition(area.x + (area.width - width) / 2, area.y + (area.height - height) / 2)
    }
    ParallelAnimation {
        id: dockAnimation
        NumberAnimation { id: dockX; target: root; property: "x"; duration: 150; easing.type: Easing.OutCubic }
        NumberAnimation { id: dockY; target: root; property: "y"; duration: 150; easing.type: Easing.OutCubic }
    }
    NumberAnimation { id: revealAnimation; target: root; property: "revealProgress"; to: 1; duration: 360; easing.type: Easing.OutCubic }
    NumberAnimation {
        id: hideAnimation
        target: root; property: "revealProgress"; to: 0; duration: 260; easing.type: Easing.InOutCubic
        onFinished: root.finishDismiss()
    }
    Connections {
        target: windowEffects
        function onInteractingChanged() { if (windowEffects.interacting) dockAnimation.stop() }
        function onMoveFinished() { root.snapToScreenEdge() }
    }
    function metric(key) { return backend.online && backend.metrics[key] !== undefined ? Math.round(backend.metrics[key]) + "%" : "—" }
    function settlePage() {
        pageOut.stop(); pageIn.stop()
        displayedTab = selectedTab
        pages.opacity = 1; pages.pageOffset = 0
    }
    function changePage() {
        if (!sceneReady) return
        if (!animationsEnabled || !visible) { settlePage(); return }
        if (pageOut.running) return // The outgoing transition uses the latest requested tab.
        if (displayedTab === selectedTab && !pageIn.running) return
        transitionDirection = selectedTab >= displayedTab ? 1 : -1
        pageIn.stop()
        pageOut.start()
    }
    SetupDialog { controller: setupController; theme: visual }
    property bool chatRequested: false
    function syncMessages() {
        const items = backend.messages
        const follow = chatList.atYEnd || chatModel.count === 0 ||
                       (items.length > 0 && items[items.length - 1].role === "user")
        if (items.length < chatModel.count) chatModel.clear()
        for (let i = 0; i < items.length; ++i) {
            const row = {speaker: items[i].role, body: items[i].text, mediaJson: JSON.stringify(items[i].attachments || []), modelName: items[i].model || ""}
            if (i >= chatModel.count) chatModel.append(row)
            else chatModel.set(i, row)
        }
        if (follow) Qt.callLater(function() { chatList.positionViewAtEnd() })
    }
    Drawer {
        id: historyPopup; objectName: "chatHistoryPopup"
        parent: Overlay.overlay; edge: Qt.LeftEdge; y: 48
        width: Math.min(320, parent.width - 64); height: parent.height - y
        modal: true; focus: true; interactive: false
        leftPadding: 18; rightPadding: 18; topPadding: 18; bottomPadding: 18
        background: Rectangle { color: visual.popup; border.color: root.line }
        Overlay.modal: Rectangle { color: root.darkMode ? "#66000000" : "#33111b2e" }
        enter: Transition { NumberAnimation { property: "position"; duration: visual.motion ? 220 : 0; easing.type: Easing.OutCubic } }
        exit: Transition { NumberAnimation { property: "position"; duration: visual.motion ? 180 : 0; easing.type: Easing.InCubic } }
        contentItem: ColumnLayout {
            spacing: 12
            RowLayout {
                Text { Layout.fillWidth: true; text: "История чата"; color: root.ink; font.pixelSize: 18; font.weight: Font.DemiBold }
                ActionButton { text: "×"; implicitWidth: 30; implicitHeight: 30; onClicked: historyPopup.close(); ToolTip.visible: hovered; ToolTip.text: "Закрыть историю" }
            }
            ActionButton { text: "+ Новый диалог"; primary: true; Layout.fillWidth: true; implicitHeight: 36; enabled: backend.online && !backend.chatsBusy && !backend.busy; onClicked: { backend.newChat(); historyPopup.close() } }
            TextField { id: historySearch; objectName: "chatHistorySearch"; Layout.fillWidth: true; placeholderText: "Найти диалог"; color: root.ink; placeholderTextColor: root.muted; selectByMouse: true; background: FieldSurface { theme: visual } }
            ListView {
                id: historyList; objectName: "chatHistoryList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 6
                model: backend.chats.filter(function(c) { return c.title.toLowerCase().includes(historySearch.text.toLowerCase()) })
                ScrollBar.vertical: UiScrollBar { theme: visual }
                delegate: ItemDelegate {
                    required property var modelData
                    width: ListView.view.width; height: 62; leftPadding: 12; rightPadding: 12
                    enabled: !backend.busy && !backend.chatsBusy
                    background: Rectangle {
                        color: modelData.id === backend.chatId || parent.hovered ? root.elevated : "transparent"; radius: 9
                        border.color: modelData.id === backend.chatId ? root.accentColor : "transparent"
                        Behavior on color { enabled: visual.motion; ColorAnimation { duration: 120 } }
                    }
                    contentItem: Column {
                        spacing: 5
                        Text { width: parent.width; text: modelData.title; color: root.ink; font.pixelSize: 13; font.weight: modelData.id === backend.chatId ? Font.DemiBold : Font.Normal; elide: Text.ElideRight }
                        Text { text: (modelData.count || 0) + " сообщений · " + new Date(modelData.updated).toLocaleDateString(Qt.locale()); color: root.muted; font.pixelSize: 10 }
                    }
                    onClicked: { backend.openChat(modelData.id); historyPopup.close() }
                }
            }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; visible: historyList.count === 0; text: backend.chatsBusy ? "Загрузка…" : historySearch.text.length ? "Диалоги не найдены" : "История пока пуста"; color: root.muted; font.pixelSize: 12 }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: root.line }
            ActionButton { text: "Очистить историю…"; Layout.fillWidth: true; implicitHeight: 32; enabled: backend.chats.length > 0 && !backend.chatsBusy && !backend.busy; onClicked: { chatConfirmation.action = "all"; chatConfirmation.open(); historyPopup.close() } }
        }
    }
    Menu {
        id: chatMenu; x: root.width - width - 24; y: 135
        MenuItem { text: "Переименовать"; onTriggered: { renameField.text = backend.chatTitle; renameDialog.open() } }
        MenuItem { text: "Очистить диалог"; onTriggered: { chatConfirmation.action = "clear"; chatConfirmation.open() } }
        MenuItem { text: "Удалить диалог"; onTriggered: { chatConfirmation.action = "delete"; chatConfirmation.open() } }
    }
    Popup {
        id: renameDialog; objectName: "renameChatDialog"; parent: Overlay.overlay
        anchors.centerIn: parent; width: Math.min(360, parent.width - 32); height: 176; padding: 16
        modal: true; focus: true
        background: SurfacePanel { theme: visual; color: visual.popup }
        contentItem: ColumnLayout {
            Text { text: "Название диалога"; color: root.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
            TextField { id: renameField; Layout.fillWidth: true; maximumLength: 100; selectByMouse: true; color: root.ink; background: FieldSurface { theme: visual } onAccepted: { if (text.trim().length) { backend.renameChat(text); renameDialog.close() } } }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                ActionButton { text: "Отмена"; implicitHeight: 34; onClicked: renameDialog.close() }
                ActionButton { text: "Сохранить"; primary: true; implicitHeight: 34; enabled: renameField.text.trim().length > 0; onClicked: { backend.renameChat(renameField.text); renameDialog.close() } }
            }
        }
    }
    Popup {
        id: chatConfirmation; objectName: "chatDeleteDialog"; parent: Overlay.overlay
        property string action: "clear"
        anchors.centerIn: parent; width: Math.min(390, parent.width - 32); height: 206; padding: 16
        modal: true; focus: true
        background: SurfacePanel { theme: visual; color: visual.popup }
        contentItem: ColumnLayout {
            spacing: 12
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: chatConfirmation.action === "all" ? "Удалить всю историю?" : chatConfirmation.action === "delete" ? "Удалить диалог?" : "Очистить диалог?"; color: root.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
            Text { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Сообщения и вложения будут удалены. Память о вас хранится отдельно на вкладке «Память»."; color: root.muted; font.pixelSize: 13 }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                ActionButton { text: "Отмена"; implicitHeight: 34; onClicked: chatConfirmation.close() }
                ActionButton { text: "Удалить"; destructive: true; implicitHeight: 34; onClicked: { if (chatConfirmation.action === "clear") backend.clearSavedChat(); else backend.deleteChat(chatConfirmation.action === "all"); chatConfirmation.close() } }
            }
        }
    }
    ListModel { id: chatModel }
    function stageAction(phrase) {
        const text = phrase.trim()
        if (!text.length) return
        composer.executeAction = true; composer.generateImage = false
        if (!composer.text.trim().length) composer.text = text
        else if (composer.text.trim() !== text) composer.text += "\n" + text
        selectedTab = 1
        Qt.callLater(function() { composer.forceActiveFocus() })
    }
    Component.onCompleted: { sceneReady = true; settlePage(); syncMessages() }
    onSelectedTabChanged: {
        changePage()
        if (selectedTab === 4 && !smokeMode) backend.refreshMemories()
        if (selectedTab === 1 && !smokeMode) { chatRequested = backend.online; backend.refreshChats() }
        if (selectedTab === 5 && !smokeMode) backend.refreshSettings()
        if (selectedTab === 6 && !smokeMode) backend.refreshProfile()
        if (selectedTab === 9 && !smokeMode) backend.refreshModels()
        if (selectedTab === 7 && !smokeMode) backend.refreshAbilities()
        if (selectedTab === 8 && !smokeMode) {
            backend.refreshProtocols()
            if (!backend.abilitiesReady) backend.refreshAbilities()
        }
    }
    onAnimationsEnabledChanged: {
        if (sceneReady && !animationsEnabled) {
            settlePage(); dockAnimation.stop(); revealAnimation.stop(); hideAnimation.stop()
            if (dismissAction.length) finishDismiss()
            else revealProgress = 1
        }
    }
    onVisibleChanged: if (sceneReady && !visible) {
        settlePage(); dockAnimation.stop(); revealAnimation.stop(); hideAnimation.stop()
        if (dismissAction.length) finishDismiss()
        else revealProgress = 1
    }
    onVisibilityChanged: function(visibility) {
        const previous = previousVisibility
        previousVisibility = visibility
        if (visibility !== Window.Windowed) dockAnimation.stop()
        if (sceneReady && visibility === Window.Minimized) {
            revealAnimation.stop(); hideAnimation.stop()
            if (dismissAction.length) finishDismiss()
            else revealProgress = 1
        } else if (sceneReady && previous === Window.Minimized && !pendingQuit) {
            revealProgress = animationsEnabled ? 0 : 1
            Qt.callLater(function() {
                if (!root.dismissAction.length && root.visible && visual.motion) revealAnimation.start()
            })
        }
    }
    Connections {
        target: backend
        function onStateChanged() {
            if (!backend.online) root.chatRequested = false
            else if (root.selectedTab === 1 && !smokeMode && !root.chatRequested) { root.chatRequested = true; backend.refreshChats() }
            if (root.selectedTab === 9 && backend.online && !smokeMode && !backend.modelsBusy && !backend.modelsReady)
                backend.refreshModels()
            if (root.selectedTab === 8 && backend.online && !smokeMode && !backend.protocolsBusy && !backend.protocolsReady)
                backend.refreshProtocols()
            if ((root.selectedTab === 7 || root.selectedTab === 8) && backend.online && !smokeMode && !backend.abilitiesBusy && !backend.abilitiesReady)
                backend.refreshAbilities()
            if (root.selectedTab === 6 && backend.online && !smokeMode && !backend.profileBusy && !backend.profileReady)
                backend.refreshProfile()
            if (root.selectedTab === 4 && backend.online && !smokeMode && !backend.memoryBusy && backend.memoryKinds.length === 0)
                backend.refreshMemories()
            if (root.selectedTab === 5 && backend.online && !smokeMode && !backend.settingsBusy && Object.keys(backend.settings).length === 0)
                backend.refreshSettings()
        }
        function onMemoryAdded() { memoryPage.clearDraft() }
        function onMessagesChanged() { root.syncMessages() }
        function onChatSent() { composer.clear() }
        function onChatsChanged() {
            const caps = backend.chatCapabilities.capabilities || ({})
            if (!caps.image_generation) composer.generateImage = false
            else if (caps.text === false) composer.generateImage = true
        }
    }
    onClosing: function(close) {
        if (closeApproved) return
        if (hideToTray && trayAvailable) {
            close.accepted = false
            root.hideToBackground()
        } else if (visual.motion) {
            close.accepted = false
            root.dismissWindow("close")
        }
    }

    component CopyLabel: TextEdit { font.family: visual.fontFamily;
        color: root.ink; font.pixelSize: 14; readOnly: true; selectByMouse: true
        wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
    }
    component ActionButton: UiButton { theme: visual }
    component Card: SurfacePanel {
        id: card
        theme: visual
        property bool hoverable: false
        property real lift: hoverable && cardHover.hovered ? -3 : 0
        border.color: hoverable && cardHover.hovered ? Qt.alpha(root.accentColor, 0.65) : root.line
        transform: Translate { y: card.lift }
        HoverHandler { id: cardHover; enabled: card.hoverable }
        Behavior on lift { enabled: root.animationsEnabled; NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Behavior on border.color { enabled: root.animationsEnabled; ColorAnimation { duration: 160 } }
    }
    component MetricCard: Card {
        property string caption
        property string value
        property real percentage: 0
        hoverable: true
        implicitHeight: 112
        ColumnLayout {
            anchors.fill: parent; anchors.margins: 16; spacing: 8
            Text { font.family: visual.fontFamily; text: caption; color: root.muted; font.pixelSize: 13 }
            Text { font.family: visual.fontFamily; text: value; color: root.ink; font.pixelSize: 26; font.weight: Font.DemiBold }
            Rectangle {
                Layout.fillWidth: true; height: 4; radius: 2; color: root.elevated
                Rectangle { height: 4; radius: 2; color: root.accentColor; width: parent.width * Math.min(100, Math.max(0, percentage)) / 100; Behavior on width { enabled: root.animationsEnabled; NumberAnimation { duration: 350; easing.type: Easing.OutCubic } } }
            }
        }
    }
    component ThemeTile: Button {
        id: tile
        property bool dark: true
        readonly property bool chosen: root.darkMode === dark
        implicitWidth: 160; implicitHeight: 82; padding: 12; hoverEnabled: true
        text: dark ? "Тёмная" : "Светлая"
        Accessible.name: text + " тема"
        onClicked: { root.darkMode = dark; root.persist() }
        scale: down ? 0.97 : hovered ? 1.02 : 1
        Behavior on scale { enabled: root.animationsEnabled; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: 12; color: tile.dark ? "#10151f" : "#f1f4f9"
            border.width: tile.chosen || tile.activeFocus ? 2 : 1
            border.color: tile.chosen || tile.activeFocus ? root.accentColor : root.line
            Behavior on border.color { enabled: root.animationsEnabled; ColorAnimation { duration: 180 } }
        }
        contentItem: ColumnLayout {
            spacing: 10
            RowLayout {
                spacing: 7; Layout.fillWidth: true; Layout.fillHeight: true
                Rectangle { Layout.preferredWidth: 28; Layout.fillHeight: true; radius: 4; color: tile.dark ? "#25344e" : "#dbe4f2" }
                ColumnLayout {
                    spacing: 6; Layout.fillWidth: true
                    Rectangle { Layout.fillWidth: true; height: 8; radius: 4; color: root.accentColor; opacity: 0.85 }
                    Rectangle { Layout.fillWidth: true; height: 20; radius: 4; color: tile.dark ? "#25344e" : "#dbe4f2" }
                }
            }
            RowLayout {
                Text { font.family: visual.fontFamily; text: tile.text; color: tile.dark ? "#edf2fb" : "#172238"; font.pixelSize: 13; font.weight: Font.DemiBold }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 14; height: 14; radius: 7; color: tile.chosen ? root.accentColor : "transparent"
                    border.color: tile.chosen ? root.accentColor : (tile.dark ? "#9baac1" : "#52637e")
                    Rectangle { anchors.centerIn: parent; width: 4; height: 4; radius: 2; color: "white"; visible: tile.chosen }
                }
            }
        }
    }
    component PreferenceSwitch: Switch {
        id: toggle
        hoverEnabled: true
        spacing: 12; padding: 6
        implicitHeight: 42
        opacity: enabled ? 1 : 0.45
        HoverHandler { cursorShape: toggle.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
        indicator: Rectangle {
            implicitWidth: 40; implicitHeight: 24
            x: toggle.leftPadding; y: (toggle.height - height) / 2
            radius: 12; color: toggle.checked ? root.accentColor : root.elevated
            border.color: toggle.activeFocus ? root.ink : toggle.checked ? root.accentColor : root.line
            Behavior on color { enabled: root.animationsEnabled; ColorAnimation { duration: 160 } }
            Rectangle {
                x: toggle.checked ? 19 : 3; y: 3; width: 18; height: 18; radius: 9
                color: toggle.checked ? "white" : root.muted
                Behavior on x { enabled: root.animationsEnabled; NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
        }
        contentItem: Text { font.family: visual.fontFamily;
            text: toggle.text; color: root.ink; font.pixelSize: 14
            leftPadding: toggle.indicator.width + toggle.spacing
            verticalAlignment: Text.AlignVCenter
        }
    }
    component StyleTile: Button {
        id: tile
        required property var definition
        readonly property var preview: Styles.palette(definition, root.darkMode)
        objectName: "styleTile-" + definition.id
        readonly property bool chosen: root.styleId === definition.id
        text: definition.name; Accessible.name: text + " стиль"
        implicitWidth: 140; implicitHeight: 100; padding: 12; hoverEnabled: true
        scale: down ? 0.97 : 1
        Behavior on scale { enabled: visual.motion; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        onClicked: { root.styleId = definition.id; root.persist() }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: tile.definition.controlRadius; color: tile.preview.bg
            border.color: tile.chosen || tile.activeFocus ? root.accentColor : root.line
            border.width: tile.chosen ? 2 : 1
            Behavior on color { enabled: visual.motion; ColorAnimation { duration: 160 } }
            Behavior on border.color { enabled: visual.motion; ColorAnimation { duration: 160 } }
        }
        contentItem: ColumnLayout {
            spacing: 12
            RowLayout {
                Layout.fillWidth: true; spacing: 6
                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        Layout.fillWidth: true; height: 34; radius: tile.definition.controlRadius / 2
                        color: index === 0 ? tile.preview.accent : tile.preview.elevated
                        border.color: index === 0 ? "transparent" : tile.preview.line
                        Text { anchors.centerIn: parent; text: index === 0 && tile.definition.decoration === "terminal" ? ">_" : ""; color: tile.preview.bg; font.family: tile.definition.fontFamily; font.pixelSize: 17 }
                    }
                }
            }
            Text { text: tile.text; color: tile.preview.ink; font.family: tile.definition.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold }
        }
    }

    RowLayout {
        anchors.fill: parent; anchors.margins: 8; anchors.topMargin: 0; spacing: 0
        transform: Translate { y: (1 - root.revealProgress) * 8 }
        Rectangle {
            objectName: "navigationRail"
            Layout.preferredWidth: root.navigationWidth; Layout.minimumWidth: root.navigationWidth; Layout.maximumWidth: root.navigationWidth; Layout.fillHeight: true; clip: true
            radius: Math.min(16, visual.cardRadius); color: root.sidebar
            border.color: Qt.alpha(root.line, 0.65)
            AppNavigation {
                anchors.fill: parent; theme: visual; client: backend
                titles: root.tabs; selectedTab: root.selectedTab; expanded: root.navigationExpanded
                onActivated: function(tab) { root.selectedTab = tab }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            StackLayout {
                id: pages
                objectName: "pages"
                property real pageOffset: 0
                transform: Translate { y: pages.pageOffset }
                enabled: !pageOut.running
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.minimumHeight: 0; Layout.minimumWidth: 0
                Layout.leftMargin: 12; Layout.rightMargin: 4; Layout.topMargin: 8; Layout.bottomMargin: 4
                currentIndex: root.displayedTab

                ParallelAnimation {
                    id: pageOut
                    NumberAnimation { target: pages; property: "opacity"; to: 0; duration: 80; easing.type: Easing.InQuad }
                    NumberAnimation { target: pages; property: "pageOffset"; to: -8 * root.transitionDirection; duration: 80; easing.type: Easing.InQuad }
                    onFinished: {
                        root.displayedTab = root.selectedTab
                        pages.pageOffset = 16 * root.transitionDirection
                        pageIn.start()
                    }
                }
                ParallelAnimation {
                    id: pageIn
                    NumberAnimation { target: pages; property: "opacity"; to: 1; duration: 210; easing.type: Easing.OutCubic }
                    NumberAnimation { target: pages; property: "pageOffset"; to: 0; duration: 240; easing.type: Easing.OutCubic }
                }

                // Home
                ScrollView {
                    id: homeScroll
                    contentWidth: availableWidth; clip: true; rightPadding: 12
                    ScrollBar.vertical: UiScrollBar {
                        theme: visual; parent: homeScroll
                        x: homeScroll.width - width; y: homeScroll.topPadding; height: homeScroll.availableHeight
                    }
                    ColumnLayout {
                        width: parent.width; spacing: 12
                        Card {
                            Layout.fillWidth: true; implicitHeight: 132
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 18; spacing: 12
                                RowLayout {
                                    Text { text: "ScottAI"; color: root.ink; font.family: visual.fontFamily; font.pixelSize: 22; font.weight: Font.DemiBold }
                                    Item { Layout.fillWidth: true }
                                    Text { text: backend.status; color: backend.online ? visual.success : root.muted; font.family: visual.fontFamily; font.pixelSize: 12 }
                                }
                                RowLayout {
                                    ActionButton { text: "Диалог"; primary: true; enabled: backend.online; onClicked: { root.selectedTab = 1; composer.forceActiveFocus() } }
                                    ActionButton { text: "Память"; onClicked: root.selectedTab = 4 }
                                    Item { Layout.fillWidth: true }
                                    ActionButton { text: backend.starting ? "Запуск…" : "Запустить Scott"; visible: !backend.online; enabled: !backend.starting; onClicked: backend.startBackend() }
                                }
                            }
                        }
                        RowLayout {
                            spacing: 12; Layout.fillWidth: true
                            MetricCard { Layout.fillWidth: true; caption: "Процессор"; value: root.metric("cpu"); percentage: backend.metrics.cpu || 0 }
                            MetricCard { Layout.fillWidth: true; caption: "Память"; value: root.metric("ram"); percentage: backend.metrics.ram || 0 }
                            MetricCard { Layout.fillWidth: true; caption: "Видеокарта"; value: root.metric("gpu"); percentage: backend.metrics.gpu || 0 }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            Repeater {
                                model: ["Что ты умеешь?", "Нагрузка компьютера", "Свободная память"]
                                ActionButton {
                                    required property string modelData
                                    Layout.fillWidth: true; Layout.minimumWidth: 0; text: modelData
                                    onClicked: { root.selectedTab = 1; composer.text = modelData; composer.forceActiveFocus() }
                                }
                            }
                        }
                        UiNotice { theme: visual; text: backend.error; error: true; Layout.fillWidth: true }
                    }
                }

                // Chat
                ColumnLayout {
                    spacing: 8
                    RowLayout {
                        ActionButton { objectName: "chatHistoryButton"; text: "История"; implicitHeight: 32; enabled: !backend.busy && !backend.chatsBusy; onClicked: { if (!smokeMode) backend.refreshChats(); historyPopup.open() } ToolTip.visible: hovered; ToolTip.text: "История чата" }
                        Text { Layout.fillWidth: true; Layout.minimumWidth: 0; text: backend.chatTitle || "Новый диалог"; color: root.ink; font.pixelSize: 15; font.weight: Font.DemiBold; elide: Text.ElideRight }
                        ActionButton { text: "+ Новый"; implicitHeight: 32; enabled: backend.online && !backend.busy && !backend.chatsBusy; onClicked: backend.newChat(); ToolTip.visible: hovered; ToolTip.text: "Новый диалог" }
                        ActionButton { text: "···"; implicitHeight: 32; implicitWidth: 34; enabled: !backend.busy && !backend.chatsBusy && backend.chatId.length > 0; onClicked: chatMenu.open(); ToolTip.visible: hovered; ToolTip.text: "Действия с диалогом" }
                    }
                    RowLayout {
                        spacing: 8
                        Text { Layout.fillWidth: true; Layout.minimumWidth: 0; text: backend.chatCapabilities.model || "Выберите модель"; elide: Text.ElideMiddle; color: root.muted; font.pixelSize: 11 }
                        ActionButton { text: "Модель ↗"; implicitHeight: 26; enabled: !backend.busy; onClicked: root.selectedTab = 9; ToolTip.visible: hovered; ToolTip.text: "Выбор модели и её возможности" }
                    }
                    RowLayout {
                        visible: root.chatCapabilityWarning.length > 0
                        Layout.fillWidth: true
                        UiNotice { objectName: "chatCapabilityNotice"; theme: visual; warning: true; text: root.chatCapabilityWarning; Layout.fillWidth: true }
                        ActionButton { objectName: "chatWarningModelsButton"; text: "Модели"; implicitHeight: 30; enabled: !backend.busy; onClicked: root.selectedTab = 9 }
                        ActionButton { text: "×"; implicitWidth: 26; implicitHeight: 30; visible: root.chatWarningFeature.length > 0; onClicked: root.chatWarningFeature = "" }
                    }
                    Card {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Column {
                            anchors.centerIn: parent; spacing: 12; visible: backend.messages.length === 0
                            Image { anchors.horizontalCenter: parent.horizontalCenter; width: 72; height: 72; source: root.lightIcon ? "qrc:/brand/scott-logo-light.png" : "qrc:/brand/scott-logo.png" }
                            Text { font.family: visual.fontFamily; anchors.horizontalCenter: parent.horizontalCenter; text: "Напишите Scott"; color: root.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                            Text { font.family: visual.fontFamily; anchors.horizontalCenter: parent.horizontalCenter; text: backend.online ? "" : "Запустите Scott на вкладке «Система»."; color: root.muted; font.pixelSize: 13 }
                        }
                        ListView {
                            id: chatList
                            objectName: "chatList"
                            anchors.fill: parent; anchors.margins: 18; anchors.rightMargin: 28
                            spacing: 16; clip: true; model: chatModel
                            ScrollBar.vertical: UiScrollBar { theme: visual }
                            add: Transition {
                                enabled: root.animationsEnabled && root.visible && root.displayedTab === 1
                                ParallelAnimation {
                                    NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
                                    NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 260; easing.type: Easing.OutCubic }
                                }
                            }
                            delegate: Item {
                                id: message
                                required property int index
                                objectName: "chatMessage" + index
                                required property string speaker
                                required property string body
                                required property string mediaJson
                                required property string modelName
                                width: ListView.view.width; height: bubble.height
                                transformOrigin: speaker === "user" ? Item.BottomRight : Item.BottomLeft
                                Rectangle {
                                    id: bubble
                                    width: Math.min(parent.width * 0.86, 700)
                                    height: messageContent.implicitHeight + 32
                                    anchors.right: message.speaker === "user" ? parent.right : undefined
                                    radius: visual.controlRadius + 2
                                    Behavior on radius { enabled: visual.motion; NumberAnimation { duration: 220 } }
                                    color: message.speaker === "user" ? root.elevated : root.bg
                                    border.color: message.speaker === "error" ? "#ae6653" : root.line
                                    ColumnLayout {
                                        id: messageContent
                                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 8
                                        Text { font.family: visual.fontFamily; text: message.speaker === "user" ? "ВЫ" : message.speaker === "error" ? "НЕ УДАЛОСЬ ОТПРАВИТЬ" : "SCOTT"; color: root.accentColor; font.pixelSize: 10; font.weight: Font.Bold; font.letterSpacing: 1 }
                                        CopyLabel { Layout.fillWidth: true; text: message.body }
                                        Repeater {
                                            model: JSON.parse(message.mediaJson)
                                            delegate: ColumnLayout {
                                                required property var modelData
                                                Layout.fillWidth: true; spacing: 5
                                                Image { Layout.fillWidth: true; Layout.preferredHeight: 180; visible: modelData.mime.indexOf("image/") === 0; source: visible ? modelData.url : ""; fillMode: Image.PreserveAspectFit; asynchronous: true }
                                                RowLayout {
                                                    Text { Layout.fillWidth: true; Layout.minimumWidth: 0; text: modelData.name; color: root.muted; font.pixelSize: 11; elide: Text.ElideMiddle }
                                                    ActionButton { visible: message.speaker === "assistant" && modelData.mime.indexOf("image/") === 0; text: "Сохранить"; implicitHeight: 28; onClicked: backend.saveChatImage(modelData.url) }
                                                }
                                            }
                                        }
                                        Text { Layout.fillWidth: true; visible: message.modelName.length > 0 && message.speaker === "assistant"; text: message.modelName; color: root.muted; font.pixelSize: 9; elide: Text.ElideMiddle }
                                    }
                                }
                            }
                        }
                    }
                    RowLayout {
                        spacing: 7
                        Repeater {
                            model: 3
                            delegate: Rectangle {
                                id: thinkingDot
                                required property int index
                                visible: backend.busy; width: 5; height: 5; radius: 3; color: root.accentColor
                                SequentialAnimation on opacity {
                                    running: backend.busy && root.visible && root.selectedTab === 1 && root.animationsEnabled
                                    loops: Animation.Infinite
                                    PauseAnimation { duration: thinkingDot.index * 120 }
                                    NumberAnimation { to: 0.2; duration: 280 }
                                    NumberAnimation { to: 1; duration: 280 }
                                    PauseAnimation { duration: (2 - thinkingDot.index) * 120 }
                                    onStopped: thinkingDot.opacity = 1
                                }
                            }
                        }
                        Text { Layout.fillWidth: true; wrapMode: Text.Wrap; font.family: visual.fontFamily; text: backend.busy ? (composer.generateImage ? "Scott создаёт изображение…" : "Scott готовит ответ…") : !backend.online ? "Нет подключения к Scott" : backend.chatNotice || "Enter — отправить · Shift + Enter — новая строка"; color: root.muted; font.pixelSize: 11 }
                    }
                    Card {
                        Layout.fillWidth: true; implicitHeight: backend.attachments.length ? 154 : 116
                        border.color: composer.activeFocus ? root.accentColor : root.line
                        Rectangle {
                            anchors.fill: parent; anchors.margins: -3; radius: parent.radius + 3
                            color: "transparent"; border.width: 2; border.color: root.accentColor
                            opacity: composer.activeFocus ? 0.20 : 0
                            Behavior on opacity { enabled: visual.motion; NumberAnimation { duration: 180 } }
                        }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 10; spacing: 4
                            RowLayout {
                                visible: backend.attachments.length > 0; Layout.fillWidth: true
                                Repeater {
                                    model: backend.attachments
                                    delegate: Rectangle {
                                        required property var modelData
                                        required property int index
                                        Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: 38
                                        radius: 7; color: root.elevated; border.color: root.line
                                        RowLayout {
                                            anchors.fill: parent; anchors.margins: 4
                                            Image { visible: modelData.mime.indexOf("image/") === 0; Layout.preferredWidth: 30; Layout.preferredHeight: 30; source: visible ? modelData.url : ""; fillMode: Image.PreserveAspectFit; asynchronous: true }
                                            Text { Layout.fillWidth: true; Layout.minimumWidth: 0; text: modelData.name; color: root.ink; font.pixelSize: 11; elide: Text.ElideMiddle }
                                            ActionButton { text: "×"; implicitWidth: 24; implicitHeight: 26; leftPadding: 4; rightPadding: 4; enabled: !backend.busy; onClicked: backend.removeAttachment(index) }
                                        }
                                    }
                                }
                            }
                            ScrollView {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                TextArea { font.family: visual.fontFamily;
                                    id: composer; objectName: "chatComposer"
                                    property bool generateImage: false
                                    property bool executeAction: false
                                    placeholderText: generateImage ? "Опишите изображение…" : executeAction ? "Команда для Scott…" : "Сообщение или вопрос о файле…"; placeholderTextColor: root.muted
                                    color: root.ink; wrapMode: TextEdit.Wrap; selectByMouse: true
                                    background: null
                                    function submit() { if (!backend.busy && !backend.chatsBusy && backend.online && (text.trim().length > 0 || backend.attachments.length > 0)) backend.sendChatMessage(text, generateImage, executeAction) }
                                    Keys.onReturnPressed: function(event) { if (!(event.modifiers & Qt.ShiftModifier)) { submit(); event.accepted = true } else event.accepted = false }
                                    Keys.onEnterPressed: function(event) { if (!(event.modifiers & Qt.ShiftModifier)) { submit(); event.accepted = true } else event.accepted = false }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                ActionButton { objectName: "attachFileButton"; text: "+ Файл"; implicitHeight: 30; enabled: !backend.busy && !composer.generateImage && !composer.executeAction; opacity: (backend.chatCapabilities.capabilities || {}).documents === true ? 1 : 0.65; onClicked: if (root.requestChatFeature("documents")) backend.chooseAttachments(false); ToolTip.visible: hovered; ToolTip.text: CapabilityInfo.description(backend.chatCapabilities.capabilities || ({}), "documents") }
                                ActionButton { objectName: "attachPhotoButton"; text: "Фото"; implicitHeight: 30; enabled: !backend.busy && !composer.generateImage && !composer.executeAction; opacity: (backend.chatCapabilities.capabilities || {}).images === true ? 1 : 0.65; onClicked: if (root.requestChatFeature("images")) backend.chooseAttachments(true); ToolTip.visible: hovered; ToolTip.text: CapabilityInfo.description(backend.chatCapabilities.capabilities || ({}), "images") }
                                ActionButton { text: composer.executeAction ? "Действие ✓" : "Действие"; primary: composer.executeAction; implicitHeight: 30; enabled: !backend.busy && backend.attachments.length === 0; onClicked: { composer.executeAction = !composer.executeAction; composer.generateImage = false } }
                                ActionButton {
                                    objectName: "generateImageButton"
                                    text: composer.generateImage ? "Картинка ✓" : "Картинка"
                                    primary: composer.generateImage; implicitHeight: 30
                                    opacity: (backend.chatCapabilities.capabilities || {}).image_generation === true ? 1 : 0.65
                                    enabled: !backend.busy && backend.attachments.length === 0
                                    onClicked: { if (root.requestChatFeature("image_generation")) { composer.generateImage = !composer.generateImage; composer.executeAction = false } }
                                    ToolTip.visible: hovered
                                    ToolTip.text: CapabilityInfo.description(backend.chatCapabilities.capabilities || ({}), "image_generation")
                                }
                                Item { Layout.fillWidth: true }
                                ActionButton { text: "↑"; primary: true; implicitWidth: 36; implicitHeight: 30; enabled: backend.online && !backend.busy && !backend.chatsBusy && (composer.text.trim().length > 0 || backend.attachments.length > 0); onClicked: composer.submit(); ToolTip.visible: hovered; ToolTip.text: "Отправить" }
                            }
                        }
                        DropArea { anchors.fill: parent; onDropped: function(drop) { if (drop.hasUrls && !composer.generateImage && !composer.executeAction) { backend.stageAttachments(drop.urls); drop.acceptProposedAction() } } }
                    }
                }

                // System
                ColumnLayout {
                    spacing: 18
                    GridLayout {
                        Layout.fillWidth: true; columns: 2; columnSpacing: 16; rowSpacing: 16
                        Repeater {
                            model: [{name:"Процессор", key:"cpu"}, {name:"Оперативная память", key:"ram"}, {name:"Видеокарта", key:"gpu"}, {name:"Нагрузка на диск", key:"disk"}]
                            delegate: MetricCard { required property var modelData; Layout.fillWidth: true; caption: modelData.name; value: root.metric(modelData.key); percentage: backend.metrics[modelData.key] || 0 }
                        }
                    }
                    Card {
                        Layout.fillWidth: true; implicitHeight: 106
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 16; spacing: 10
                            Text { font.family: visual.fontFamily; text: "Подключение"; color: root.ink; font.pixelSize: 17; font.weight: Font.DemiBold }
                            RowLayout {
                                Text { font.family: visual.fontFamily; text: backend.status; color: root.muted; Layout.fillWidth: true }
                                ActionButton { text: "Обновить"; onClicked: backend.refresh() }
                                ActionButton { text: "Запустить"; enabled: !backend.online && !backend.starting; onClicked: backend.startBackend() }
                                ActionButton { text: "Остановить"; visible: backend.ownsBackend; onClicked: backend.stopBackend() }
                            }
                        }
                    }
                    UiNotice { theme: visual; text: backend.error; error: true; Layout.fillWidth: true }
                    Item { Layout.fillHeight: true }
                }

                // Appearance
                ScrollView {
                    id: appearanceScroll
                    objectName: "appearanceScroll"
                    contentWidth: availableWidth; clip: true; rightPadding: 12
                    ScrollBar.vertical: UiScrollBar {
                        theme: visual; parent: appearanceScroll
                        x: appearanceScroll.width - width; y: appearanceScroll.topPadding; height: appearanceScroll.availableHeight
                    }
                    ColumnLayout {
                        width: parent.width; spacing: 12
                        Card {
                            Layout.fillWidth: true; implicitHeight: 146
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 12
                                Text { font.family: visual.fontFamily; text: "Тема окна"; color: root.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                                RowLayout {
                                    spacing: 12
                                    ThemeTile { dark: true }
                                    ThemeTile { dark: false }
                                    Item { Layout.fillWidth: true }
                                    Image { source: root.lightIcon ? "qrc:/brand/scott-logo-light.png" : "qrc:/brand/scott-logo.png"; Layout.preferredWidth: 60; Layout.preferredHeight: 60 }
                                }
                            }
                        }
                        Card {
                            Layout.fillWidth: true; implicitHeight: styleGrid.implicitHeight + 62
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 12
                                Text { font.family: visual.fontFamily; text: "Стиль интерфейса"; color: root.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                                GridLayout {
                                    id: styleGrid
                                    Layout.fillWidth: true; columns: 3; columnSpacing: 12; rowSpacing: 12
                                    Repeater {
                                        model: Styles.styles
                                        StyleTile { required property var modelData; definition: modelData; Layout.fillWidth: true }
                                    }
                                }
                            }
                        }
                        Card {
                            Layout.fillWidth: true; implicitHeight: 116
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 12
                                Text { font.family: visual.fontFamily; text: "Акцентный цвет"; color: root.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                                RowLayout {
                                    spacing: 14
                                    Repeater {
                                        model: ["#5588ff", "#b078f5", "#248866", "#b87324", "#cb5967", "#168591"]
                                        delegate: Button {
                                            id: swatch
                                            required property string modelData
                                            implicitWidth: 40; implicitHeight: 40
                                            hoverEnabled: true
                                            scale: down ? 0.94 : hovered ? 1.12 : 1
                                            Behavior on scale { enabled: root.animationsEnabled; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                                            Accessible.name: "Акцент " + modelData
                                            background: Rectangle {
                                                radius: 20; color: modelData
                                                border.width: root.accentOverride === modelData || swatch.activeFocus ? 3 : 0; border.color: root.ink
                                                Behavior on border.width { enabled: root.animationsEnabled; NumberAnimation { duration: 140 } }
                                            }
                                            onClicked: { root.accentOverride = modelData; root.persist() }
                                        }
                                    }
                                    ActionButton { text: "По стилю"; primary: root.accentOverride.length === 0; onClicked: { root.accentOverride = ""; root.persist() } }
                                }
                            }
                        }
                        Card {
                            objectName: "glassFrostCard"
                            visible: root.glassActive
                            Layout.fillWidth: true; implicitHeight: 142
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 8
                                RowLayout {
                                    Text { text: "Матовость стекла"; color: root.ink; font.family: visual.fontFamily; font.pixelSize: 15; font.weight: Font.DemiBold }
                                    Item { Layout.fillWidth: true }
                                    Text { text: root.glassFrost + "%"; color: root.accentColor; font.family: visual.fontFamily; font.pixelSize: 15 }
                                }
                                UiSlider {
                                    objectName: "glassFrostSlider"
                                    theme: visual; Layout.fillWidth: true; value: root.glassFrost
                                    Accessible.name: "Матовость стекла в процентах"
                                    onMoved: { root.glassFrost = Math.round(value); glassFrostSave.restart() }
                                }
                                Text { text: windowEffects.available
                                    ? "0% — прозрачное · 100% — матовое"
                                    : "Размытие недоступно: меняется плотность фона.";
                                    color: root.muted; font.family: visual.fontFamily; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                            Timer { id: glassFrostSave; interval: 300; onTriggered: root.persist() }
                        }
                        Card {
                            objectName: "transparencyCard"
                            Layout.fillWidth: true; implicitHeight: 142
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 8
                                RowLayout {
                                    Text { font.family: visual.fontFamily; text: "Прозрачность панелей"; color: root.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                                    Item { Layout.fillWidth: true }
                                    Text { font.family: visual.fontFamily; text: root.panelTransparency + "%"; color: root.accentColor; font.pixelSize: 15 }
                                }
                                UiSlider {
                                    id: transparencySlider; objectName: "transparencySlider"
                                    theme: visual; Layout.fillWidth: true; value: root.panelTransparency
                                    Accessible.name: "Прозрачность панелей в процентах"
                                    onMoved: { root.setPanelTransparency(value); transparencySave.restart() }
                                }
                                RowLayout {
                                    Text { font.family: visual.fontFamily; text: "0% — непрозрачные · 100% — виден фон окна"; color: root.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    ActionButton { text: "По стилю"; implicitHeight: 34; onClicked: { const values = Object.assign({}, root.transparencyByStyle); delete values[root.styleDefinition.id]; root.transparencyByStyle = values; root.persist() } }
                                }
                            }
                            Timer { id: transparencySave; interval: 300; onTriggered: root.persist() }
                        }
                        Card {
                            Layout.fillWidth: true; implicitHeight: 112
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16; spacing: 12
                                Text { font.family: visual.fontFamily; text: "Значок приложения"; color: root.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                                RowLayout {
                                    spacing: 12
                                    ActionButton { text: "Тёмный значок"; primary: !root.lightIcon; onClicked: { root.lightIcon = false; root.persist() } }
                                    ActionButton { text: "Светлый значок"; primary: root.lightIcon; onClicked: { root.lightIcon = true; root.persist() } }
                                }
                            }
                        }
                        PreferenceSwitch {
                            text: "Плавные анимации"; checked: root.animationsEnabled
                            onToggled: { root.animationsEnabled = checked; root.persist() }
                        }
                        PreferenceSwitch {
                            text: "Закрывать в трей"; checked: root.hideToTray; enabled: trayAvailable
                            onToggled: { root.hideToTray = checked; root.persist() }
                        }
                    }
                }
                MemoryPage {
                    id: memoryPage
                    objectName: "memoryPage"
                    client: backend
                    theme: visual
                    darkMode: root.darkMode
                    animationsEnabled: root.animationsEnabled
                    bg: root.bg; surface: root.surface; elevated: root.elevated
                    ink: root.ink; muted: root.muted; line: root.line; accent: root.accentColor
                }
                SettingsPage {
                    objectName: "settingsPage"; client: backend; theme: visual
                    backgroundAllowed: trayAvailable; backgroundEnabled: root.hideToTray
                    notificationsEnabled: root.trayNotifications
                    onNotificationsChanged: function(enabled) { root.trayNotifications = enabled; root.persistWorkspace() }
                    onBackgroundChanged: function(enabled) { root.hideToTray = enabled; root.persist() }
                    onResetAppearanceRequested: root.resetAppearance()
                }
                ProfilePage {
                    objectName: "profilePage"; client: backend; avatar: profileAvatar; theme: visual
                }
                ActionsPage {
                    objectName: "actionsPage"; client: backend; theme: visual
                    onPhraseRequested: function(phrase) { root.stageAction(phrase) }
                }
                ProtocolsPage {
                    objectName:"protocolsPage"; client:backend; files:protocolFiles; theme:visual
                }
                ModelsPage {
                    objectName: "modelsPage"; client: backend; theme: visual
                }
            }
        }
    }
}
