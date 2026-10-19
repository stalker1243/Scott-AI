.pragma library
var pets = [
    {id:"scott",name:QT_TRANSLATE_NOOP("Launcher", "Скотт Младший"),detail:QT_TRANSLATE_NOOP("Launcher", "Маленький разработчик"),action:QT_TRANSLATE_NOOP("Launcher", "Открыть терминал"),colors:["blue","black","white","green"]}
]
var colors = {blue:"#68abff",black:"#627386",white:"#e7f4ff",green:"#68ebac",scarlet:"#ec5369",red:"#ff7757",cyan:"#65dfff"}
var colorNames = {blue:QT_TRANSLATE_NOOP("Launcher", "Синий"),black:QT_TRANSLATE_NOOP("Launcher", "Чёрный"),white:QT_TRANSLATE_NOOP("Launcher", "Белый"),green:QT_TRANSLATE_NOOP("Launcher", "Зелёный"),scarlet:QT_TRANSLATE_NOOP("Launcher", "Алый"),red:QT_TRANSLATE_NOOP("Launcher", "Красный"),cyan:QT_TRANSLATE_NOOP("Launcher", "Голубой")}
function find(id) { for (var i=0;i<pets.length;++i) if (pets[i].id===id) return pets[i];return pets[0] }
function color(id) { return colors[id] || colors.blue }
