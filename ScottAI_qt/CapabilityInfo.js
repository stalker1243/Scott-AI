.pragma library

function name(feature) {
    return ({documents: qsTranslate("Launcher", "работа с файлами"), images: qsTranslate("Launcher", "анализ фотографий"),
             video: qsTranslate("Launcher", "анализ видео"), image_generation: qsTranslate("Launcher", "генерация изображений")})[feature] || qsTranslate("Launcher", "эта функция")
}

function reason(state, feature) {
    if (!state || !state.model)
        return qsTranslate("Launcher", "Выберите модель и добавьте API Token на вкладке «Модели».")
    if (state.enabled === false)
        return qsTranslate("Launcher", "Подключите выбранную модель на вкладке «Модели».")
    var caps = state.capabilities || ({})
    if (caps[feature] === true) return ""
    if (caps.known !== true)
        return qsTranslate("Launcher", "Для модели «%1» поддержка функции «%2» не подтверждена. Выберите модель с соответствующим значком.").replace(/%([12])/g, function(_, index) { return index === "1" ? state.model : name(feature) })
    return qsTranslate("Launcher", "Модель «%1» не поддерживает функцию «%2». Выберите подходящую модель на вкладке «Модели».").replace(/%([12])/g, function(_, index) { return index === "1" ? state.model : name(feature) })
}

function description(caps, feature) {
    if (caps[feature] !== true)
        return caps.known === true ? qsTranslate("Launcher", "Модель не поддерживает: ") + name(feature) : qsTranslate("Launcher", "Поддержка не подтверждена: ") + name(feature)
    return ({documents: qsTranslate("Launcher", "Текст из PDF, DOCX и исходного кода"), images: qsTranslate("Launcher", "Модель анализирует фотографии"),
             video: qsTranslate("Launcher", "Модель анализирует видео"), image_generation: qsTranslate("Launcher", "Модель создаёт изображения по описанию")})[feature]
}
