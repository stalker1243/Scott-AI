#pragma once
#include <QObject>
#include <QNetworkAccessManager>
#include <QTimer>
#include <QVariantList>
#include <QVariantMap>
#include <QProcess>
#include <QUrl>
#include <QJsonObject>
#include <functional>

class BackendClient : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool online READ online NOTIFY stateChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY stateChanged)
    Q_PROPERTY(bool starting READ starting NOTIFY stateChanged)
    Q_PROPERTY(bool ownsBackend READ ownsBackend NOTIFY stateChanged)
    Q_PROPERTY(QString status READ status NOTIFY stateChanged)
    Q_PROPERTY(QString error READ error NOTIFY stateChanged)
    Q_PROPERTY(QVariantMap metrics READ metrics NOTIFY metricsChanged)
    Q_PROPERTY(QVariantList messages READ messages NOTIFY messagesChanged)
    Q_PROPERTY(QVariantList chats READ chats NOTIFY chatsChanged)
    Q_PROPERTY(QString chatId READ chatId NOTIFY chatsChanged)
    Q_PROPERTY(QString chatTitle READ chatTitle NOTIFY chatsChanged)
    Q_PROPERTY(bool chatsBusy READ chatsBusy NOTIFY chatsChanged)
    Q_PROPERTY(QVariantMap chatCapabilities READ chatCapabilities NOTIFY chatsChanged)
    Q_PROPERTY(QVariantList attachments READ attachments NOTIFY attachmentsChanged)
    Q_PROPERTY(QString chatNotice READ chatNotice NOTIFY chatsChanged)
    Q_PROPERTY(QVariantList memories READ memories NOTIFY memoriesChanged)
    Q_PROPERTY(QVariantList memoryKinds READ memoryKinds NOTIFY memoriesChanged)
    Q_PROPERTY(bool memoryBusy READ memoryBusy NOTIFY memoryStateChanged)
    Q_PROPERTY(bool autoMemoryEnabled READ autoMemoryEnabled NOTIFY memoriesChanged)
    Q_PROPERTY(bool memorySettingsAvailable READ memorySettingsAvailable NOTIFY memoriesChanged)
    Q_PROPERTY(int archivedTurns READ archivedTurns NOTIFY memoriesChanged)
    Q_PROPERTY(QString memoryError READ memoryError NOTIFY memoryStateChanged)
    Q_PROPERTY(QString memoryNotice READ memoryNotice NOTIFY memoryStateChanged)
    Q_PROPERTY(QVariantMap settings READ settings NOTIFY settingsChanged)
    Q_PROPERTY(QStringList settingsReady READ settingsReady NOTIFY settingsStateChanged)
    Q_PROPERTY(bool settingsBusy READ settingsBusy NOTIFY settingsStateChanged)
    Q_PROPERTY(QString settingsError READ settingsError NOTIFY settingsStateChanged)
    Q_PROPERTY(QString settingsNotice READ settingsNotice NOTIFY settingsStateChanged)
    Q_PROPERTY(QVariantMap voiceInstall READ voiceInstall NOTIFY voiceInstallChanged)
    Q_PROPERTY(bool voiceInstallReady READ voiceInstallReady NOTIFY voiceInstallChanged)
    Q_PROPERTY(QVariantMap voicePreparation READ voicePreparation NOTIFY voicePreparationChanged)
    Q_PROPERTY(bool voicePreparationReady READ voicePreparationReady NOTIFY voicePreparationChanged)
    Q_PROPERTY(bool listening READ listening NOTIFY listeningChanged)
    Q_PROPERTY(bool listeningAvailable READ listeningAvailable NOTIFY listeningChanged)
    Q_PROPERTY(bool listeningReady READ listeningReady NOTIFY listeningChanged)
    Q_PROPERTY(bool listeningBusy READ listeningBusy NOTIFY listeningChanged)
    Q_PROPERTY(QString listeningError READ listeningError NOTIFY listeningChanged)
    Q_PROPERTY(QVariantMap profile READ profile NOTIFY profileChanged)
    Q_PROPERTY(bool profileReady READ profileReady NOTIFY profileStateChanged)
    Q_PROPERTY(bool profileBusy READ profileBusy NOTIFY profileStateChanged)
    Q_PROPERTY(QString profileError READ profileError NOTIFY profileStateChanged)
    Q_PROPERTY(QString profileNotice READ profileNotice NOTIFY profileStateChanged)
    Q_PROPERTY(QVariantList abilities READ abilities NOTIFY abilitiesChanged)
    Q_PROPERTY(int abilitiesReadyCount READ abilitiesReadyCount NOTIFY abilitiesChanged)
    Q_PROPERTY(int abilitiesTotal READ abilitiesTotal NOTIFY abilitiesChanged)
    Q_PROPERTY(bool abilitiesReady READ abilitiesReady NOTIFY abilitiesStateChanged)
    Q_PROPERTY(bool abilitiesBusy READ abilitiesBusy NOTIFY abilitiesStateChanged)
    Q_PROPERTY(QString abilitiesError READ abilitiesError NOTIFY abilitiesStateChanged)
    Q_PROPERTY(QVariantList aiProviders READ aiProviders NOTIFY modelsChanged)
    Q_PROPERTY(QVariantMap aiState READ aiState NOTIFY modelsChanged)
    Q_PROPERTY(bool modelsReady READ modelsReady NOTIFY modelsStateChanged)
    Q_PROPERTY(bool modelsBusy READ modelsBusy NOTIFY modelsStateChanged)
    Q_PROPERTY(QString modelsError READ modelsError NOTIFY modelsStateChanged)
    Q_PROPERTY(QString modelsNotice READ modelsNotice NOTIFY modelsStateChanged)
    Q_PROPERTY(QVariantList protocols READ protocols NOTIFY protocolsChanged)
    Q_PROPERTY(bool protocolsReady READ protocolsReady NOTIFY protocolsStateChanged)
    Q_PROPERTY(bool protocolsBusy READ protocolsBusy NOTIFY protocolsStateChanged)
    Q_PROPERTY(QString protocolsError READ protocolsError NOTIFY protocolsStateChanged)
    Q_PROPERTY(QString protocolsNotice READ protocolsNotice NOTIFY protocolsStateChanged)
    Q_PROPERTY(QVariantMap protocolJob READ protocolJob NOTIFY protocolJobChanged)
    Q_PROPERTY(bool protocolRunning READ protocolRunning NOTIFY protocolJobChanged)
    Q_PROPERTY(bool protocolJobReady READ protocolJobReady NOTIFY protocolJobChanged)
    Q_PROPERTY(bool protocolJobBusy READ protocolJobBusy NOTIFY protocolJobChanged)
    Q_PROPERTY(QString protocolJobError READ protocolJobError NOTIFY protocolJobChanged)
public:
    QVariantMap voiceInstall() const { return m_voiceInstall; }
    bool voiceInstallReady() const { return m_voiceInstallReady; }
    QVariantMap voicePreparation() const { return m_voicePreparation; }
    bool voicePreparationReady() const { return m_voicePreparationReady; }
    explicit BackendClient(QUrl base = QUrl("http://127.0.0.1:8000"), QObject *parent = nullptr);
    ~BackendClient() override;
    bool online() const { return m_online; }
    bool busy() const { return m_busy; }
    bool starting() const { return m_starting; }
    bool ownsBackend() const { return m_process.state() != QProcess::NotRunning; }
    QString status() const;
    QString error() const { return m_error; }
    QVariantMap metrics() const { return m_metrics; }
    QVariantList messages() const { return m_messages; }
    QVariantList chats() const { return m_chats; }
    QString chatId() const { return m_chatId; }
    QString chatTitle() const { return m_chatTitle; }
    bool chatsBusy() const { return m_chatsBusy; }
    QVariantMap chatCapabilities() const { return m_chatCapabilities; }
    QVariantList attachments() const { return m_attachments; }
    QString chatNotice() const { return m_chatNotice; }
    QVariantList memories() const { return m_memories; }
    QVariantList memoryKinds() const { return m_memoryKinds; }
    bool memoryBusy() const { return m_memoryBusy; }
    bool autoMemoryEnabled() const { return m_autoMemoryEnabled; }
    bool memorySettingsAvailable() const { return m_memorySettingsAvailable; }
    int archivedTurns() const { return m_archivedTurns; }
    QString memoryError() const { return m_memoryError; }
    QString memoryNotice() const { return m_memoryNotice; }
    QVariantMap settings() const { return m_settings; }
    QStringList settingsReady() const { return m_settingsReady; }
    bool settingsBusy() const { return m_settingsBusy; }
    QString settingsError() const { return m_settingsError; }
    QString settingsNotice() const { return m_settingsNotice; }
    bool listening() const { return m_listening; }
    bool listeningAvailable() const { return m_listeningAvailable; }
    bool listeningReady() const { return m_listeningReady; }
    bool listeningBusy() const { return m_listeningBusy; }
    QString listeningError() const { return m_listeningError; }
    QVariantMap profile() const { return m_profile; }
    bool profileReady() const { return m_profileReady; }
    bool profileBusy() const { return m_profileBusy; }
    QString profileError() const { return m_profileError; }
    QString profileNotice() const { return m_profileNotice; }
    QVariantList abilities() const { return m_abilities; }
    int abilitiesReadyCount() const { return m_abilitiesReadyCount; }
    int abilitiesTotal() const { return m_abilitiesTotal; }
    bool abilitiesReady() const { return m_abilitiesReady; }
    bool abilitiesBusy() const { return m_abilitiesBusy; }
    QString abilitiesError() const { return m_abilitiesError; }
    QVariantList aiProviders() const { return m_aiProviders; }
    QVariantMap aiState() const { return m_aiState; }
    bool modelsReady() const { return m_modelsReady; }
    bool modelsBusy() const { return m_modelsBusy; }
    QString modelsError() const { return m_modelsError; }
    QString modelsNotice() const { return m_modelsNotice; }
    QVariantList protocols() const { return m_protocols; }
    bool protocolsReady() const { return m_protocolsReady; }
    bool protocolsBusy() const { return m_protocolsBusy; }
    QString protocolsError() const { return m_protocolsError; }
    QString protocolsNotice() const { return m_protocolsNotice; }
    QVariantMap protocolJob() const { return m_protocolJob; }
    bool protocolRunning() const { return QStringList{"running", "cancelling"}.contains(m_protocolJob.value("state").toString()); }
    bool protocolJobReady() const { return m_protocolJobReady; }
    bool protocolJobBusy() const { return m_protocolJobBusy; }
    QString protocolJobError() const { return m_protocolJobError; }
    void configureProcess(const QString &directory, const QString &python);
    void beginPolling();
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void sendMessage(const QString &text);
    Q_INVOKABLE void clearChat();
    Q_INVOKABLE void refreshChats();
    Q_INVOKABLE void refreshChatCapabilities();
    Q_INVOKABLE void newChat();
    Q_INVOKABLE void openChat(const QString &id);
    Q_INVOKABLE void renameChat(const QString &title);
    Q_INVOKABLE void deleteChat(bool all = false);
    Q_INVOKABLE void clearSavedChat();
    Q_INVOKABLE void chooseAttachments(bool photos = false);
    Q_INVOKABLE void stageAttachments(const QList<QUrl> &urls);
    Q_INVOKABLE void removeAttachment(int index);
    Q_INVOKABLE void sendChatMessage(const QString &text, bool image = false, bool command = false);
    Q_INVOKABLE void saveChatImage(const QString &url);
    Q_INVOKABLE void startBackend();
    Q_INVOKABLE void stopBackend();
    Q_INVOKABLE void refreshMemories();
    Q_INVOKABLE void setAutoMemoryEnabled(bool enabled);
    Q_INVOKABLE void clearConversationMemory();
    Q_INVOKABLE void addMemory(const QString &text, const QString &kind);
    Q_INVOKABLE void forgetMemory(const QString &id);
    Q_INVOKABLE void refreshSettings();
    Q_INVOKABLE void applySetting(const QString &group, const QVariantMap &changes);
    Q_INVOKABLE void previewVoice();
    Q_INVOKABLE void refreshVoiceInstall();
    Q_INVOKABLE void prepareScottVoice(bool checkOnly = false);
    Q_INVOKABLE void cancelScottVoice();
    Q_INVOKABLE void refreshVoicePreparation();
    Q_INVOKABLE void warmScottVoice();
    Q_INVOKABLE void releaseScottVoice();
    Q_INVOKABLE void refreshListening();
    Q_INVOKABLE void setListening(bool enabled);
    Q_INVOKABLE void refreshProfile();
    Q_INVOKABLE void refreshAbilities();
    Q_INVOKABLE void refreshModels();
    Q_INVOKABLE void configureModel(const QString &provider, const QString &model, const QString &apiKey);
    Q_INVOKABLE void refreshProtocols();
    Q_INVOKABLE void saveProtocol(const QString &id, const QString &json);
    Q_INVOKABLE void deleteProtocol(const QString &id);
    Q_INVOKABLE void runProtocol(const QString &id);
    Q_INVOKABLE void cancelProtocol();
    Q_INVOKABLE void saveProfile(const QString &name, const QString &about, const QString &style, const QStringList &interests);
signals:
    void voiceInstallChanged();
    void voicePreparationChanged();
    void stateChanged();
    void metricsChanged();
    void messagesChanged();
    void chatsChanged();
    void attachmentsChanged();
    void chatSent();
    void memoriesChanged();
    void memoryStateChanged();
    void memoryAdded();
    void settingsChanged();
    void settingsStateChanged();
    void listeningChanged();
    void listeningFailed(const QString &message);
    void profileChanged();
    void profileStateChanged();
    void profileSaved();
    void abilitiesChanged();
    void abilitiesStateChanged();
    void modelsChanged();
    void modelsStateChanged();
    void modelConfigured();
    void protocolsChanged();
    void protocolsStateChanged();
    void protocolSaved(const QVariantMap &protocol);
    void protocolDeleted(const QString &id);
    void protocolJobChanged();
private:
    void acceptVoiceInstall(const QJsonObject &job);
    using Callback = std::function<void(const QJsonObject &, const QString &)>;
    void request(const QString &path, const QJsonObject *body, int timeout, Callback callback, bool remove = false, bool form = false, bool patch = false);
    void loadSettings();
    bool beginSettingsOperation();
    void loadMemories();
    bool beginMemoryOperation();
    void append(const QString &role, const QString &text);
    bool acceptChat(const QJsonObject &chat);
    QString unsupportedChatFeature(const QString &feature) const;
    void chatMutation(const QString &path, const QJsonObject *body, bool remove = false, bool patch = false);
    bool beginProtocolOperation();
    void pollProtocolJob();
    void acceptProtocolJob(const QJsonObject &job);
    QUrl m_base;
    QNetworkAccessManager m_network;
    QTimer m_poll;
    QTimer m_voiceInstallPoll;
    QVariantMap m_voiceInstall;
    bool m_voiceInstallReady = false, m_voiceInstallFetching = false, m_voiceInstallPending = false;
    quint64 m_voiceInstallRevision = 0;
    QTimer m_voicePreparationPoll;
    QVariantMap m_voicePreparation;
    bool m_voicePreparationReady = false, m_voicePreparationFetching = false, m_voicePreparationPending = false;
    quint64 m_voicePreparationRevision = 0;
    bool acceptVoicePreparation(const QJsonObject &data);
    QProcess m_process;
    QString m_directory, m_python, m_error;
    bool m_online = false, m_busy = false, m_starting = false, m_refreshing = false;
    QVariantMap m_metrics;
    QVariantList m_messages;
    QVariantList m_chats, m_attachments;
    QVariantMap m_chatCapabilities;
    QString m_chatId, m_chatTitle, m_chatNotice;
    bool m_chatsBusy = false, m_chatsReady = false;
    quint64 m_chatCapabilitiesGeneration = 0;
    QVariantList m_memories, m_memoryKinds;
    bool m_memoryBusy = false;
    bool m_autoMemoryEnabled = true, m_memorySettingsAvailable = false;
    int m_archivedTurns = -1;
    QString m_memoryError, m_memoryNotice;
    QVariantMap m_settings;
    QStringList m_settingsReady;
    bool m_settingsBusy = false;
    QString m_settingsError, m_settingsNotice;
    bool m_listening = false, m_listeningAvailable = false, m_listeningReady = false, m_listeningBusy = false;
    QString m_listeningError;
    QVariantMap m_profile;
    bool m_profileReady = false, m_profileBusy = false;
    QString m_profileError, m_profileNotice;
    QVariantList m_abilities;
    int m_abilitiesReadyCount = 0, m_abilitiesTotal = 0;
    bool m_abilitiesReady = false, m_abilitiesBusy = false;
    QString m_abilitiesError;
    QVariantList m_aiProviders;
    QVariantMap m_aiState;
    bool m_modelsReady = false, m_modelsBusy = false;
    QString m_modelsError, m_modelsNotice;
    quint64 m_modelsGeneration = 0;
    QVariantList m_protocols;
    bool m_protocolsReady = false, m_protocolsBusy = false;
    QString m_protocolsError, m_protocolsNotice;
    QVariantMap m_protocolJob;
    QTimer m_protocolPoll;
    bool m_protocolJobReady = false, m_protocolJobBusy = false;
    bool m_protocolPolling = false;
    quint64 m_protocolJobRevision = 0;
    QString m_protocolJobError;
};
