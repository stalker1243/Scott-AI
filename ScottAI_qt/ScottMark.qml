import QtQuick
import QtQuick.Shapes

// The Scott ribbon drawn as curves. The mark has no background or raster layer.
Item {
    id: mark
    property color color: "white"
    implicitWidth: 96
    implicitHeight: 96
    Accessible.ignored: true
    readonly property real fit: Math.min(width / 340, height / 350)

    Item {
        x: (mark.width - 340 * mark.fit) / 2
        y: (mark.height - 350 * mark.fit) / 2
        width: 340; height: 350
        scale: mark.fit; transformOrigin: Item.TopLeft
        Shape {
            x: -85; y: -85; width: 500; height: 500
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "transparent"
                fillColor: mark.color
                PathSvg {
                    path: "M179 85 H340 C352 85 361 93 369 104 L418 170 H297 C289 170 284 165 278 161 Z "
                        + "M170 89 C122 150 128 176 212 212 C241 227 278 240 309 254 C377 277 417 297 424 336 C432 367 411 398 375 410 C404 373 402 339 376 306 C348 272 301 259 255 241 C214 225 153 207 132 185 C109 165 119 131 170 89 Z "
                        + "M131 116 C88 150 81 190 88 213 C91 242 118 259 156 277 C194 298 237 314 274 333 C329 359 355 379 356 399 C357 415 346 427 322 435 C364 421 384 399 380 373 C375 350 347 335 313 319 C281 303 234 289 197 270 C153 252 122 231 116 198 C110 167 117 142 131 116 Z "
                        + "M90 336 H206 C214 336 219 342 225 348 L313 435 H194 C183 435 175 431 168 424 Z"
                }
            }
        }
    }
}
