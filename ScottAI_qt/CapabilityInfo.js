.pragma library

function name(feature) {
    return ({documents: "работа с файлами", images: "анализ фотографий",
             video: "анализ видео", image_generation: "генерация изображений"})[feature] || "эта функция"
}

function reason(state, feature) {
    if (!state || !state.model)
        return "Выберите модель и добавьте API Token на вкладке «Модели»."
    if (state.enabled === false)
        return "Подключите выбранную модель на вкладке «Модели»."
    var caps = state.capabilities || ({})
    if (caps[feature] === true) return ""
    if (caps.known !== true)
        return "Для модели «" + state.model + "» поддержка функции «" + name(feature) + "» не подтверждена. Выберите модель с соответствующим значком."
    return "Модель «" + state.model + "» не поддерживает функцию «" + name(feature) + "». Выберите подходящую модель на вкладке «Модели»."
}

function description(caps, feature) {
    if (caps[feature] !== true)
        return caps.known === true ? "Модель не поддерживает: " + name(feature) : "Поддержка не подтверждена: " + name(feature)
    return ({documents: "Текст из PDF, DOCX и исходного кода", images: "Модель анализирует фотографии",
             video: "Модель анализирует видео", image_generation: "Модель создаёт изображения по описанию"})[feature]
}
