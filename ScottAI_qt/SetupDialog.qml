import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: setupDialog
    objectName: "setupDialog"
    required property var controller
    required property QtObject theme
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(470, parent.width - 32); height: 380; padding: 26
    modal: true; focus: true; closePolicy: Popup.NoAutoClose
    visible: controller.visible
    background: SurfacePanel { theme: setupDialog.theme; color: setupDialog.theme.popup }
    contentItem: ColumnLayout {
        spacing: 14
        Image { source: "qrc:/brand/scott-logo.png"; Layout.preferredWidth: 58; Layout.preferredHeight: 58; Layout.alignment: Qt.AlignHCenter }
        Text { text: "Добро пожаловать в Scott"; color: setupDialog.theme.ink; font.family: setupDialog.theme.fontFamily; font.pixelSize: 21; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignHCenter }
        Text { text: "Одна подготовка — и можно начинать.\nПонадобится интернет и до 5 ГБ места."; color: setupDialog.theme.muted; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
        Item { Layout.fillHeight: true }
        Text { Layout.fillWidth: true; text: setupDialog.controller.error || setupDialog.controller.message; wrapMode: Text.Wrap; color: setupDialog.controller.error.length ? setupDialog.theme.danger : setupDialog.theme.ink; font.pixelSize: 12 }
        ProgressBar { Layout.fillWidth: true; value: setupDialog.controller.progress; indeterminate: setupDialog.controller.busy && value === 0 }
        UiButton { objectName: "prepareScottButton"; theme: setupDialog.theme; Layout.fillWidth: true; primary: true; text: setupDialog.controller.busy ? "Подготовка…" : setupDialog.controller.error.length ? "Повторить" : "Настроить Scott"; enabled: !setupDialog.controller.busy; onClicked: setupDialog.controller.prepare() }
    }
}
