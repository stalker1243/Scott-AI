#include "AppLanguage.h"
#include <QCoreApplication>
#include <QLocale>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QRegularExpression>
#include <QSet>

namespace {
class CatalogTranslator final : public QTranslator {
    struct Pattern {QString source;QRegularExpression match;};
    QList<Pattern> m_patterns;
public:
    CatalogTranslator(){
        QFile file(":/i18n/patterns.json");
        if(!file.open(QIODevice::ReadOnly))return;
        const QRegularExpression argument("%([1-9][0-9]?)");
        for(const auto &row:QJsonDocument::fromJson(file.readAll()).array()) {
            const auto source=row.toString();QString expression="\\A";qsizetype last=0;QSet<QString> seen;
            auto matches=argument.globalMatch(source);
            while(matches.hasNext()) {
                auto match=matches.next();auto id="a"+match.captured(1);
                expression+=QRegularExpression::escape(source.mid(last,match.capturedStart()-last));
                expression+=seen.contains(id)?"\\k<"+id+">":"(?<"+id+">.*?)";
                seen.insert(id);last=match.capturedEnd();
            }
            expression+=QRegularExpression::escape(source.mid(last))+"\\z";
            m_patterns.append({source,QRegularExpression(expression,QRegularExpression::DotMatchesEverythingOption)});
        }
    }
    QString translate(const char *context,const char *source,const char *disambiguation=nullptr,int n=-1) const override {
        auto exact=QTranslator::translate(context,source,disambiguation,n);
        if(!exact.isEmpty()||qstrcmp(context,"Launcher")!=0)return exact;
        const auto value=QString::fromUtf8(source);if(value.size()>4096)return {};
        const QRegularExpression argument("%([1-9][0-9]?)");
        for(const auto &pattern:m_patterns) {
            const auto match=pattern.match.match(value);if(!match.hasMatch())continue;
            const auto translated=QTranslator::translate(context,pattern.source.toUtf8().constData(),nullptr,n);
            if(translated.isEmpty())continue;
            QString result;qsizetype last=0;auto placeholders=argument.globalMatch(translated);
            while(placeholders.hasNext()) {
                const auto item=placeholders.next();result+=translated.mid(last,item.capturedStart()-last)+match.captured("a"+item.captured(1));last=item.capturedEnd();
            }
            return result+translated.mid(last);
        }
        return {};
    }
};
}

AppLanguage::AppLanguage(bool temporary,const QString &settingsFile,QObject *parent)
    :QObject(parent),m_temporary(temporary),m_settings(settingsFile.isEmpty()
        ?std::make_unique<QSettings>("ScottAI","QtPrototype")
        :std::make_unique<QSettings>(settingsFile,QSettings::IniFormat)) {
    const auto initial=temporary?QStringLiteral("ru"):m_settings->value("uiLanguage","ru").toString();
    if(!apply(initial,false))apply("ru",false);
    if(!temporary) {
        m_watch.setInterval(1000);
        connect(&m_watch,&QTimer::timeout,this,[this]{
            m_settings->sync();
            apply(m_settings->value("uiLanguage","ru").toString(),false);
        });
        m_watch.start();
    }
}
AppLanguage::~AppLanguage(){if(m_translator)QCoreApplication::removeTranslator(m_translator.get());}
QString AppLanguage::locale() const {
    return m_language=="de"?"de_DE":m_language=="es"?"es_ES":m_language=="en"?"en_US":"ru_RU";
}
QVariantList AppLanguage::languages() const {
    return {QVariantMap{{"id","ru"},{"title",QString::fromUtf8("Русский")}},
            QVariantMap{{"id","en"},{"title","English"}},QVariantMap{{"id","de"},{"title","Deutsch"}},
            QVariantMap{{"id","es"},{"title",QString::fromUtf8("Español")}}};
}
QString AppLanguage::text(const QString &source){return QCoreApplication::translate("Launcher",source.toUtf8().constData());}
bool AppLanguage::setLanguage(const QString &language){return apply(language,true);}
bool AppLanguage::apply(const QString &language,bool persist) {
    if(language!="ru"&&language!="en"&&language!="de"&&language!="es")return false;
    if(language==m_language)return true;
    auto translator=std::make_unique<CatalogTranslator>();
    if(!translator->load(":/i18n/ScottAI_"+language+".qm"))return false;
    // Load first: a missing catalog must not leave a half-switched interface.
    if(m_translator)QCoreApplication::removeTranslator(m_translator.get());
    m_translator=std::move(translator);QCoreApplication::installTranslator(m_translator.get());
    m_language=language;QLocale::setDefault(QLocale(locale()));
    if(persist&&!m_temporary){m_settings->setValue("uiLanguage",language);m_settings->sync();}
    emit languageChanged();return true;
}
