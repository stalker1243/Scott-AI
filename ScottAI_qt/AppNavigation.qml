import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: navigation
    required property QtObject theme
    required property var client
    required property var titles
    property bool expanded: false
    property int selectedTab: 0
    property real selectionY: 0
    signal activated(int tab)
    signal appearanceRequested()

    function updateSelection() {
        if (!settingsLink) return
        let selected = selectedTab === 5 ? settingsLink : selectedTab === 6 ? profileLink : toolsLink
        for (let i = 0; i < workLinks.count; ++i) if (workLinks.itemAt(i) && workLinks.itemAt(i).tab === selectedTab) selected = workLinks.itemAt(i)
        if (selected) selectionY = selected.mapToItem(navigation, 0, 0).y
    }
    Component.onCompleted: Qt.callLater(updateSelection)
    onSelectedTabChanged: Qt.callLater(updateSelection)
    onHeightChanged: Qt.callLater(updateSelection)
    Connections { target: navigation.theme; function onFontFamilyChanged() { Qt.callLater(navigation.updateSelection) } }

    Rectangle {
        objectName: "navSelection"
        x: 8; y: navigation.selectionY; width: navigation.width - 16; height: 36
        radius: navigation.theme.controlRadius
        color: Qt.alpha(navigation.theme.accent, 0.14)
        border.color: Qt.alpha(navigation.theme.accent, 0.18)
        Behavior on y { enabled: navigation.theme.motion; NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        Rectangle { width: 3; height: 18; radius: 2; anchors.verticalCenter: parent.verticalCenter; color: navigation.theme.accent }
    }
    component Link: Button {
        id: link
        required property int tab
        objectName: "navTab" + tab
        text: navigation.titles[tab]; checked: navigation.selectedTab === tab
        Accessible.role: Accessible.PageTab; Accessible.checked: checked
        Accessible.name: text
        Layout.fillWidth: true; implicitHeight: 36; hoverEnabled: true
        ToolTip.visible: hovered && !navigation.expanded
        ToolTip.delay: 350
        ToolTip.text: text
        onYChanged: Qt.callLater(navigation.updateSelection)
        onClicked: navigation.activated(tab)
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        background: Rectangle {
            radius: navigation.theme.controlRadius
            color: link.hovered && !link.checked ? Qt.alpha(navigation.theme.accent, 0.07) : "transparent"
            border.color: link.visualFocus ? navigation.theme.accent : "transparent"
            Behavior on color { enabled: navigation.theme.motion; ColorAnimation { duration: 140 } }
        }
        contentItem: RowLayout {
            spacing: 10
            NavIcon { symbol: link.tab === 5 ? 7 : link.tab === 6 ? 8 : link.tab === 7 ? 9 : link.tab === 8 ? 10 : link.tab === 9 ? 11 : link.tab === 10 ? 12 : link.tab; color: link.checked ? navigation.theme.accent : navigation.theme.muted; Layout.leftMargin: 8; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
            Text { visible: navigation.expanded; text: link.text; elide: Text.ElideRight; color: link.checked ? navigation.theme.ink : navigation.theme.muted; font.family: navigation.theme.fontFamily; font.pixelSize: 13; font.weight: link.checked ? Font.DemiBold : Font.Normal; Layout.fillWidth: true; Layout.minimumWidth: 0 }
            Item { visible: !navigation.expanded; Layout.fillWidth: true }
        }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 8; spacing: 4
        Repeater { id: workLinks; model: [0, 1, 4, 9]; Link { required property int modelData; tab: modelData } }
        ChatToolButton {
            id: toolsLink
            objectName: "navigationMore"
            theme: navigation.theme; text: navigation.expanded ? qsTranslate("Launcher", "Ещё  ···") : "···"
            Accessible.name: qsTranslate("Launcher", "Другие разделы"); Layout.fillWidth: true; implicitHeight: 36
            onClicked: toolsMenu.open()
            UiMenu {
                id: toolsMenu; objectName: "navigationMoreMenu"; theme: navigation.theme; x: navigation.width - 10; y: 0
                Repeater {
                    model: [2, 10, 11]
                    UiMenuItem {
                        theme: navigation.theme
                        required property int modelData
                        objectName: "navTab" + modelData
                        text: navigation.titles[modelData]
                        onTriggered: navigation.activated(modelData)
                    }
                }
            }
        }
        Item { Layout.fillHeight: true }
        Link { id: profileLink; tab: 6 }
        Link { id: settingsLink; tab: 5 }
        Button {
            id: appearanceLink
            objectName: "appearanceButton"; text: qsTranslate("Launcher", "Персонализация")
            Accessible.name: text
            Layout.fillWidth: true; implicitHeight: 38; hoverEnabled: true
            onClicked: navigation.appearanceRequested()
            ToolTip.visible: hovered && !navigation.expanded; ToolTip.text: text
            background: Rectangle { radius: navigation.theme.controlRadius; color: appearanceLink.hovered ? navigation.theme.elevated : "transparent"; border.color: appearanceLink.visualFocus ? navigation.theme.accent : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Rectangle { Layout.leftMargin: 10; width: 16; height: 16; radius: 8; color: navigation.theme.accent; border.color: Qt.alpha(navigation.theme.ink, 0.3) }
                Text { Layout.fillWidth: true; visible: navigation.expanded; text: appearanceLink.text; color: navigation.theme.muted; font.pixelSize: 12; font.family: navigation.theme.fontFamily }
                Item { Layout.fillWidth: true; visible: !navigation.expanded }
            }
        }
    }
}
