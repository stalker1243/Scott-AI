.pragma library

// Stable IDs are persisted in QSettings. Add a definition here to expose another style.
var styles = [
    {
        id: "classic", name: "Classic", description: QT_TRANSLATE_NOOP("Launcher", "Спокойные цвета и привычные формы"),
        fontFamily: "Segoe UI", cardRadius: 16, controlRadius: 10, decoration: "none",
        dark: {bg:"#181a1f", sidebar:"#121419", surface:"#22252b", elevated:"#2b2f38", ink:"#e9edf2", muted:"#a0a7b2", line:"#343941", popup:"#202329", accent:"#7096ff"},
        light: {bg:"#ffffff", sidebar:"#f5f6f8", surface:"#fafbfc", elevated:"#edf0f4", ink:"#1e242e", muted:"#677080", line:"#e0e4e9", popup:"#ffffff", accent:"#416fce"}
    },
    {
        id: "glass", name: "Glass", description: QT_TRANSLATE_NOOP("Launcher", "Матовое стекло с размытым фоном"),
        fontFamily: "Segoe UI", cardRadius: 22, controlRadius: 14, decoration: "glass",
        dark: {bg:"#0d1529", sidebar:"#d9101a30", surface:"#b324334e", elevated:"#d1384c68", ink:"#f2f7ff", muted:"#b5c5df", line:"#526f8fab", popup:"#f51c2b43", accent:"#73b9ff"},
        light: {bg:"#e7edf8", sidebar:"#d9f7fbff", surface:"#bfffffff", elevated:"#d9e3edff", ink:"#172b48", muted:"#445d7d", line:"#7390a9c9", popup:"#faeff5ff", accent:"#356ac4"}
    },
    {
        id: "terminal-pro", name: "Terminal Pro", description: QT_TRANSLATE_NOOP("Launcher", "Моноширинный шрифт и чёткие линии"),
        fontFamily: "Consolas", cardRadius: 3, controlRadius: 3, decoration: "terminal",
        dark: {bg:"#0b1110", sidebar:"#080d0c", surface:"#101a16", elevated:"#1a2c23", ink:"#d9f2e2", muted:"#91b29f", line:"#2b4537", popup:"#101a16", accent:"#75dca4"},
        light: {bg:"#edf3ee", sidebar:"#f7faf6", surface:"#f9fcf8", elevated:"#dfebe1", ink:"#183624", muted:"#4c6956", line:"#b8cdbe", popup:"#f9fcf8", accent:"#227148"}
    }
]

function resolve(id) {
    for (var i = 0; i < styles.length; ++i)
        if (styles[i].id === id) return styles[i]
    return styles[0]
}
function palette(style, dark) { return dark ? style.dark : style.light }

function accentText(color) {
    function linear(channel) { return channel <= 0.04045 ? channel / 12.92 : Math.pow((channel + 0.055) / 1.055, 2.4) }
    var luminance = 0.2126 * linear(color.r) + 0.7152 * linear(color.g) + 0.0722 * linear(color.b)
    return luminance > 0.20 ? "#081510" : "#ffffff"
}
