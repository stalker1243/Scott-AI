import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    required property QtObject theme
    readonly property url repository: "https://github.com/stalker1243/Scott-AI"
    ColumnLayout {
        anchors.centerIn: parent; width: Math.min(parent.width - 24, 540); spacing: 20
        Image { Layout.alignment: Qt.AlignHCenter; source: "qrc:/brand/scott-logo.png"; Layout.preferredWidth: 72; Layout.preferredHeight: 72 }
        Text { Layout.alignment: Qt.AlignHCenter; text: "Scott AI"; color: page.theme.ink; font.pixelSize: 30; font.weight: Font.DemiBold }
        Text { objectName: "aboutVersion"; Layout.alignment: Qt.AlignHCenter; text: "Demo · " + appVersion + qsTranslate("Launcher", " · сборка ") + appBuild; color: page.theme.muted; font.pixelSize: 13 }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: page.theme.line }
        Text { Layout.alignment: Qt.AlignHCenter; text: qsTranslate("Launcher", "Создатель — Phantom"); color: page.theme.ink; font.pixelSize: 18; font.weight: Font.DemiBold }
        Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "От личной автоматизации — к помощнику для каждого. Диалоги, голос и меньше повседневной рутины."); color: page.theme.muted; font.pixelSize: 14; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; lineHeight: 1.3 }
        UiButton { objectName: "aboutGithub"; Layout.alignment: Qt.AlignHCenter; theme: page.theme; text: qsTranslate("Launcher", "GitHub · поддержка и обратная связь ↗"); implicitHeight: 42; onClicked: Qt.openUrlExternally(page.repository) }
        Text { Layout.fillWidth: true; text: qsTranslate("Launcher", "Об ошибке или идее можно рассказать в Issues репозитория."); color: page.theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
    }
}
