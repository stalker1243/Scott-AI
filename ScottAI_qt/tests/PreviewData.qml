import QtQml

// Synthetic data for rendering only. Never opens the real backend or its files.
QtObject {
    property QtObject setupPreview: QtObject {
        property bool visible: true
        property bool busy: false
        property double progress: 0
        property string message: "Подготовим библиотеки и модели речи для вашего компьютера."
        property string error: ""
        function prepare() {}
    }
    property bool online: true
    property bool busy: false
    property bool starting: false
    property bool ownsBackend: false
    property string status: "На связи"
    property string error: ""
    signal chatSent()
    property var chats: [{id:"11111111111111111111111111111111",title:"Дизайн Scott",count:2,updated:"2026-10-06T12:00:00Z"}, {id:"22222222222222222222222222222222",title:"Рабочие заметки",count:8,updated:"2026-10-05T12:00:00Z"}]
    property string chatId: "11111111111111111111111111111111"
    property string chatTitle: "Дизайн Scott"
    property bool chatsBusy: false
    property var attachments: []
    property string chatNotice: ""
    property var chatCapabilities: ({enabled:true,model:"Scott / Demo Vision",capabilities:{known:true,text:true,documents:true,images:true,video:false,image_generation:true}})
    onChatCapabilitiesChanged: chatsChanged()
    function refreshChats() {}
    function refreshChatCapabilities() {}
    function newChat() { messages = []; chatId = "33333333333333333333333333333333"; chatTitle = "Новый диалог" }
    function openChat(id) { chatId = id }
    function renameChat(title) { chatTitle = title }
    function clearSavedChat() { messages = [] }
    function deleteChat(all) { messages = []; if (all) chats = [] }
    property int attachmentDialogsOpened: 0
    function chooseAttachments(photos) { ++attachmentDialogsOpened }
    function stageAttachments(urls) {}
    function removeAttachment(index) { attachments = attachments.filter(function(_, i) { return i !== index }) }
    function saveChatImage(url) {}
    function sendChatMessage(text, image) { ++messagesSent; chatSent() }
    property var metrics: ({cpu: 24, ram: 48, gpu: 12, disk: 6})
    property var messages: [{role: "user", text: "Что ты умеешь?"}, {role: "assistant", text: "Могу помочь с вопросами, программами и повседневными задачами."}]
    property bool memoryBusy: false
    property bool autoMemoryEnabled: true
    property bool memorySettingsAvailable: true
    property int archivedTurns: 42
    function setAutoMemoryEnabled(value) { autoMemoryEnabled = value }
    function clearConversationMemory() { archivedTurns = 0 }
    property bool protocolsReady: true
    property bool protocolsBusy: false
    property string protocolsError: ""
    property string protocolsNotice: ""
    property bool protocolJobReady: true
    property bool protocolJobBusy: false
    property string protocolJobError: ""
    property var protocolJob: ({})
    property bool protocolRunning: protocolJob.state === "running" || protocolJob.state === "cancelling"
    property int protocolWrites: 0
    property int protocolRuns: 0
    property int protocolCancels: 0
    property int protocolDeletes: 0
    property var protocolDraftSent: ({})
    property var protocols: [
        {id:"demo-protocol", name:"Рабочий день", description:"Подготовить рабочее пространство", enabled:true, repeat_count:2, stop_on_error:true, phrases:["за работу"], schedule_text:"по будням в 09:00", schedule:{hour:9,minute:0,days:[0,1,2,3,4],enabled:true}, created:"2026-10-02T10:00:00", last_run:null, runs:3, steps:[{text:"открой браузер", pause:2, enabled:true}, {text:"открой документы", pause:0, enabled:true}]},
        {id:"off-protocol", name:"Учёба", description:"Сохранённый сценарий", enabled:false, repeat_count:1, stop_on_error:false, phrases:[], schedule_text:"", schedule:null, created:"2026-10-01T10:00:00", last_run:null, runs:0, steps:[{text:"открой браузер", pause:0, enabled:true}]}
    ]
    property bool abilitiesReady: true
    property bool abilitiesBusy: false
    property string abilitiesError: ""
    property int abilitiesReadyCount: 3
    property int abilitiesTotal: 4
    property int messagesSent: 0
    property var abilities: [
        {group: "Программы и файлы", items: [{id:"open_app", title:"Открыть программу", detail:"Scott находит установленную программу по названию.", state:"ready", reason:"", examples:["открой браузер", "запусти блокнот"]}]},
        {group: "Разговор", items: [{id:"voice", title:"Слышать по имени", detail:"Голосовой помощник откликается на имя.", state:"off", reason:"Микрофонов в системе не найдено", examples:["Скотт, сколько времени"]}]},
        {group: "Компьютер", items: [{id:"power", title:"Выключение и перезагрузка", detail:"С задержкой, чтобы успеть передумать.", state:"ready", reason:"", examples:["выключи компьютер"]}]},
        {group: "Время и порядок", items: [{id:"reminders", title:"Напомнить", detail:"Через час, завтра утром или в указанное время.", state:"ready", reason:"", examples:["напомни через час позвонить маме и обсудить планы на выходные"]}]}
    ]
    property bool profileReady: true
    property bool modelsReady: true
    property bool modelsBusy: false
    property string modelsError: ""
    property string modelsNotice: ""
    property int modelWrites: 0
    property var modelLastRequest: ({})
    property var aiState: ({provider:"Groq", model:"demo-fast", enabled:true})
    property var aiProviders: [
        {id:"Groq", note:"Быстрые ответы", configured:true, models:[{id:"demo-fast", note:"Быстрая модель"}, {id:"demo-large", note:"Для сложных вопросов"}]},
        {id:"OpenAI", note:"Модели GPT", configured:false, models:[{id:"gpt-demo", note:"Пример модели"}]},
        {id:"DeepSeek", note:"Модели DeepSeek", configured:false, models:[{id:"deepseek-chat", note:"Диалог"}]},
        {id:"Anthropic", note:"Модели Claude", configured:false, models:[{id:"claude-demo", note:"Пример модели"}]},
        {id:"OpenRouter", note:"Один ключ для моделей разных поставщиков", configured:false, models:[{id:"vendor/free-demo", free:true, note:"Бесплатная модель"}, {id:"vendor/large-demo", note:"Крупная модель"}]}
    ]
    property bool profileBusy: false
    property string profileError: ""
    property string profileNotice: ""
    property int profileWrites: 0
    property var profile: ({name:"Тестовый профиль", about:"Изучаю программирование и создаю приложения.", style:"friendly", interests:["C++", "Музыка"], styles:[{id:"friendly", title:"Дружелюбный", hint:"Просто и тепло"}, {id:"brief", title:"Краткий", hint:"Коротко и по делу"}]})
    property string memoryError: ""
    property string memoryNotice: ""
    property bool settingsBusy: false
    property var voiceInstall: ({state:"idle",installed:false,supported:true,message:""})
    property var voicePreparation: ({id:"",state:"idle",model_loaded:false,message:""})
    property bool voicePreparationReady: true
    function refreshVoicePreparation() {}
    function warmScottVoice() { voicePreparation = {id:"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",state:"complete",model_loaded:true,message:"Scott Voice готов к речи."} }
    function releaseScottVoice() { voicePreparation = {id:"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",state:"cancelled",model_loaded:false,message:"Модель освобождена."} }
    property bool voiceInstallReady: true
    function refreshVoiceInstall() {}
    function prepareScottVoice(checkOnly) { voiceInstall = {id:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",state:"running",installed:false,supported:true,message:"Устанавливаем библиотеки голоса"} }
    function cancelScottVoice() { voiceInstall = {state:"cancelled",installed:false,supported:true,message:"Подготовка отменена. Её можно продолжить позже."} }
    property string settingsError: ""
    property string settingsNotice: ""
    property int settingsWrites: 0
    property string settingsLastGroup: ""
    property var settingsLastChanges: ({})
    property var settingsReady: ["audio", "device", "voices", "characters", "versions"]
    property var settings: ({
        audio: {available:true, settings:{volume:75, quiet:false, input_device:"", output_device:"", character:"natural"}, devices:{input:[{name:"Микрофон USB", default:true}], output:[{name:"Наушники", default:true}]}},
        device: {cuda_available:false, rocm_available:true, engines:{
            whisper:{choice:"auto", device:"cuda", device_label:"AMD (ROCm/HIP)", locked_by_env:false, options:[
                {id:"auto",title:"Авто",available:true}, {id:"cuda",title:"NVIDIA",available:false},
                {id:"rocm",title:"AMD",available:true}, {id:"cpu",title:"Процессор",available:true}]},
            silero:{choice:"cpu", device:"cpu", device_label:"процессор", locked_by_env:true, env_var:"SILERO_DEVICE", options:[
                {id:"auto",title:"Авто",available:true}, {id:"cuda",title:"NVIDIA",available:false},
                {id:"rocm",title:"AMD",available:true}, {id:"mps",title:"Apple",available:false},
                {id:"cpu",title:"Процессор",available:true}]}}},
        voices: {current:"demo", voices:[{id:"demo", label:"Пробный голос", local:true}, {id:"cloud", label:"Облачный голос", local:false}]},
        characters: {current:"calm", characters:[{id:"natural", title:"Естественный"}, {id:"calm", title:"Спокойный — мягкий и чёткий"}, {id:"radio", title:"Радио"}]},
        versions: {data:[{item_id:"example_macro", item_type:"macro", versions_count:3}]}
    })
    property var memoryKinds: [{id:"fact", title:"Факты"}, {id:"preference", title:"Предпочтения"}, {id:"task", title:"Задачи"}, {id:"note", title:"Заметки"}]
    property var memories: [
        {id:"demo1", text:"Предпочитаю короткие ответы с конкретными примерами.", kind:"preference", created:1790769600},
        {id:"demo2", text:"Изучаю C++ и создаю настольное приложение на Qt.", kind:"fact", source:"conversation", created:1790683200},
        {id:"demo3", text:"Проверить новую версию интерфейса на небольшом экране и убедиться, что длинные записи переносятся без обрезания текста.", kind:"task", created:1790596800}
    ]
    signal stateChanged()
    signal memoryAdded()
    signal settingsStateChanged()
    signal profileStateChanged()
    signal profileSaved()
    signal modelsChanged()
    signal modelsStateChanged()
    signal modelConfigured()
    signal abilitiesStateChanged()
    signal protocolsStateChanged()
    signal protocolSaved(var protocol)
    signal protocolDeleted(string id)
    function refresh() {}
    function refreshMemories() {}
    function refreshSettings() {}
    function refreshProfile() {}
    function refreshModels() { modelsChanged() }
    function configureModel(provider, model, key) {
        ++modelWrites; modelLastRequest = {provider:provider, model:model, has_key:key.trim().length > 0}
        aiState = {provider:provider, model:model, enabled:true}
        aiProviders = aiProviders.map(function(p) { return p.id === provider ? Object.assign({}, p, {configured:true}) : p })
        modelsNotice = "Настройки сохранены. Модель подключена."
        modelConfigured(); modelsChanged()
    }
    function refreshAbilities() {}
    function refreshProtocols() {}
    function saveProtocol(id, json) { ++protocolWrites; protocolDraftSent = JSON.parse(json) }
    function deleteProtocol(id) { ++protocolDeletes }
    function runProtocol(id) {
        ++protocolRuns
        protocolJob = {id:"fixture-job", protocol_id:id, name:"Рабочий день", state:"running", current:1, total:4, text:"открой браузер", message:"Выполняю протокол…", error:"", steps:[{text:"открой браузер", ok:true, response:"Программа открыта", index:0, iteration:1}]}
    }
    function cancelProtocol() {
        ++protocolCancels
        protocolJob = Object.assign({}, protocolJob, {state:"cancelled", message:"Выполнение остановлено. Завершённые действия сохранены."})
    }
    function saveProfile(name, about, style, interests) { ++profileWrites }
    function applySetting(group, changes) {
        ++settingsWrites; settingsLastGroup = group; settingsLastChanges = changes
        if (group === "voiceStreaming") {
            settings = Object.assign({}, settings, {voices:Object.assign({}, settings.voices, {scott_streaming:changes.streaming})})
        }
        if (group === "voiceAcceleration") {
            settings = Object.assign({}, settings, {voices:Object.assign({}, settings.voices, {scott_acceleration:changes.acceleration})})
        }
        if (group === "voiceBuffer") {
            settings = Object.assign({}, settings, {voices:Object.assign({}, settings.voices, {scott_buffer:changes.buffer})})
        }
        if (group === "voiceProfile") {
            settings = Object.assign({}, settings, {voices:Object.assign({}, settings.voices, {scott_profile:changes.profile})})
        }
    }
    function previewVoice() { ++settingsWrites }
    function sendMessage(text) { ++messagesSent }
    function appendDemoMessage() {
        messages = messages.concat([{role: "assistant", text: "Новое сообщение появляется плавно. Предыдущие сообщения остаются на месте."}])
    }
    function clearChat() { messages = [] }
    function startBackend() {}
    function stopBackend() {}
    function addMemory(text, kind) {}
    function forgetMemory(id) {}
}
