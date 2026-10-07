import QtQuick

Canvas {
    id: backdrop
    required property QtObject theme
    visible: theme.decoration === "terminal"
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Connections {
        target: backdrop.theme
        function onDecorationChanged() { backdrop.requestPaint() }
        function onDarkChanged() { backdrop.requestPaint() }
        function onAccentChanged() { backdrop.requestPaint() }
    }
    onPaint: {
        const ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        if (theme.decoration === "terminal") {
            ctx.strokeStyle = Qt.alpha(theme.accent, theme.dark ? 0.055 : 0.075)
            ctx.lineWidth = 1
            ctx.beginPath()
            for (let x = 0.5; x < width; x += 32) { ctx.moveTo(x, 0); ctx.lineTo(x, height) }
            for (let y = 0.5; y < height; y += 32) { ctx.moveTo(0, y); ctx.lineTo(width, y) }
            ctx.stroke()
        }
    }
}
