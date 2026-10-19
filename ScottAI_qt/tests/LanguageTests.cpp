#include "AppLanguage.h"
#include <QtTest>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QTemporaryDir>
#include <QFile>
#include <QRegularExpression>

class LanguageTests:public QObject {
    Q_OBJECT
private slots:
    void switchWithoutRecreatingDraft(){
        AppLanguage language(true);QQmlEngine engine;
        connect(&language,&AppLanguage::languageChanged,&engine,&QQmlEngine::retranslate);
        QQmlComponent component(&engine);component.setData("import QtQml\nQtObject { property string title: qsTranslate(\"Launcher\", \"Настройки\"); property string draft: \"unchanged user content\" }",{});
        QScopedPointer<QObject> object(component.create());QVERIFY2(object,qPrintable(component.errorString()));
        const QStringList codes{"ru","en","de","es","ru"},labels{QString::fromUtf8("Настройки"),"Settings","Einstellungen","Ajustes",QString::fromUtf8("Настройки")};
        for(int i=0;i<codes.size();++i){
            QVERIFY(language.setLanguage(codes[i]));QCOMPARE(object->property("title").toString(),labels[i]);
            QCOMPARE(object->property("draft").toString(),QString("unchanged user content"));
            QCOMPARE(QLocale().name(),language.locale());
        }
        QVERIFY(!language.setLanguage("../fr"));QCOMPARE(language.language(),QString("ru"));
    }
    void persistentChoiceAndNoTemporaryWrites(){
        QTemporaryDir dir;const auto file=dir.filePath("settings.ini");
        {AppLanguage language(false,file);QVERIFY(language.setLanguage("de"));}
        const auto original=[&]{QFile f(file);f.open(QIODevice::ReadOnly);return f.readAll();}();
        {AppLanguage language(true,file);QCOMPARE(language.language(),QString("ru"));QVERIFY(language.setLanguage("es"));}
        {QFile f(file);QVERIFY(f.open(QIODevice::ReadOnly));QCOMPARE(f.readAll(),original);}
        {AppLanguage language(false,file);QCOMPARE(language.language(),QString("de"));}
    }
    void formattedNoticesPreserveOpaqueValues(){
        AppLanguage language(true);QVERIFY(language.setLanguage("en"));
        const auto source=QString::fromUtf8("Backend завершился. Код: %1").arg(27);
        QCOMPARE(AppLanguage::text(source),QString("The backend exited. Code: 27"));
        QCOMPARE(AppLanguage::text("opaque user text <token>&42"),QString("opaque user text <token>&42"));
        QCOMPARE(AppLanguage::text(QString::fromUtf8("Не удалось запустить Python: opaque %1 & 42")),QString("Could not start Python: opaque %1 & 42"));
    }
    void setupCapacityAndDownloadMessages(){
        AppLanguage language(true);
        const auto capacity=QString::fromUtf8("Чат и голос: примерно 3–4 ГиБ. Для подготовки оставьте 4,5 ГиБ свободно. Оценка для стандартной модели речи; другие модели требуют больше места.");
        const auto transfer=QString::fromUtf8("Скачиваю PyTorch: 12.5 / 2482.2 МиБ. При обрыве можно продолжить.");
        const auto lowSpace=QString::fromUtf8("Недостаточно места на диске установки: свободно 1 ГиБ, для новой подготовки нужно около 4,5 ГиБ. Освободите место и повторите подготовку.");
        const QRegularExpression russian(QString::fromUtf8("[А-Яа-яЁё]"));
        for(const auto &code:QStringList{"en","de","es"}){
            QVERIFY(language.setLanguage(code));
            const auto hint=AppLanguage::text(capacity),progress=AppLanguage::text(transfer),error=AppLanguage::text(lowSpace);
            QVERIFY(hint.contains("3–4 GiB"));QVERIFY(hint.contains("4,5 GiB"));
            QVERIFY(progress.contains("12.5 / 2482.2 MiB"));QVERIFY(error.contains("4,5 GiB"));
            QVERIFY(!russian.match(hint+progress+error).hasMatch());
        }
    }
};
QTEST_GUILESS_MAIN(LanguageTests)
#include "LanguageTests.moc"
