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

    function updateSelection() {
        if (!appearanceLink) return
        let selected = selectedTab === 5 ? settingsLink : appearanceLink
        for (let i = 0; i < workLinks.count; ++i) if (workLinks.itemAt(i) && workLinks.itemAt(i).tab === selectedTab) selected = workLinks.itemAt(i)
        for (let i = 0; i < managementLinks.count; ++i) if (managementLinks.itemAt(i) && managementLinks.itemAt(i).tab === selectedTab) selected = managementLinks.itemAt(i)
        if (selected) selectionY = selected.mapToItem(navigation, 0, 0).y
    }
    Component.onCompleted: Qt.callLater(updateSelection)
    onSelectedTabChanged: Qt.callLater(updateSelection)
    onHeightChanged: Qt.callLater(updateSelection)
    Connections { target: navigation.theme; function onFontFamilyChanged() { Qt.callLater(navigation.updateSelection) } }

    Rectangle {
        objectName: "navSelection"
        x: 8; y: navigation.selectionY; width: navigation.width - 16; height: 40
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
        Layout.fillWidth: true; implicitHeight: 40; hoverEnabled: true
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
            NavIcon { symbol: link.tab === 5 ? 7 : link.tab === 6 ? 8 : link.tab === 7 ? 9 : link.tab === 8 ? 10 : link.tab === 9 ? 11 : link.tab; color: link.checked ? navigation.theme.accent : navigation.theme.muted; Layout.leftMargin: 8; Layout.preferredWidth: 20; Layout.preferredHeight: 20 }
            Text { visible: navigation.expanded; text: link.text; elide: Text.ElideRight; color: link.checked ? navigation.theme.ink : navigation.theme.muted; font.family: navigation.theme.fontFamily; font.pixelSize: 13; font.weight: link.checked ? Font.DemiBold : Font.Normal; Layout.fillWidth: true; Layout.minimumWidth: 0 }
            Item { visible: !navigation.expanded; Layout.fillWidth: true }
        }
    }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 8; spacing: 6
        Repeater { id: workLinks; model: [0, 1, 7, 8, 4]; Link { required property int modelData; tab: modelData } }
        Rectangle { Layout.fillWidth: true; height: 1; color: navigation.theme.line; Layout.topMargin: 4; Layout.bottomMargin: 4 }
        Repeater { id: managementLinks; model: [9, 2, 6]; Link { required property int modelData; tab: modelData } }
        Item { Layout.fillHeight: true }
        Link { id: appearanceLink; tab: 3 }
        Link { id: settingsLink; tab: 5 }
    }
}
