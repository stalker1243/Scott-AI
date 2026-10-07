# Логотип Scott AI

Новый знак — монохромная буква S из двух изогнутых лент.

- `scott-icon-master.png`: белый знак на чёрном фоне.
- `scott-icon-light-master.png`: чёрный знак на белом фоне.

Мастера подготовлены встроенным ImageGen по двум логотипам пользователя
от 30 сентября 2026 года. Поля уменьшены для отображения в приложении.
Это подготовленные версии изображений, а не неизменённые исходные вложения.

## Экспорт

Из корня проекта на Windows:

```powershell
powershell -ExecutionPolicy Bypass -File installer/export_icons.ps1
```

Нужен только Windows PowerShell с System.Drawing. Каждый размер вычисляется
из мастера отдельно с качественным уменьшением. ICO содержит PNG-кадры
16, 20, 24, 32, 40, 48, 64, 128 и 256 пикселей. Отдельные PNG до 1024 пикселей
используются интерфейсом и сборщиками дистрибутивов.

Скрипт обновляет оба набора в `ScottAI_avalonia/Assets` и копии в мобильном
проекте. Windows EXE и установщик используют `scott.ico`, Linux — `icon-256.png`,
macOS — PNG 128–1024. README выбирает светлую или тёмную версию по теме браузера.
В приложении пользователь выбирает вариант независимо от темы окна.

## Запросы ImageGen

### Тёмный вариант

Prepare this supplied Scott AI logo as a production app icon master. Edit target: the attached white ribbon S on black. Preserve the EXACT existing distinctive S silhouette and proportions, including its two curving bands and sharp diagonal terminals. Only adjust framing: center the existing mark and enlarge it to occupy 78% of square canvas width/height, equal optical margins. Flat pure white mark on pure black rounded-square tile with subtly rounded corners (radius 16% canvas width), actual transparent pixels outside tile corners. No shadow, glow, texture, gradients, outlines, lettering, extra objects, mockup, or new design. One square 1024x1024 icon asset, full bleed tile. Faithfully preserve input logo identity.

### Светлый вариант

Prepare this supplied Scott AI logo as a production light app icon master. Edit target: attached black ribbon S on white. Preserve EXACT existing distinctive S silhouette and proportions, two curving bands, diagonal terminals. Only framing adjustment: center the existing mark and enlarge to occupy about 70% square canvas width/height with equal optical margins, matching dark companion. Flat black mark on flat pure white square background. No shadow, glow, texture, gradient, outlines, lettering, mockups, extra objects or new design. Output single square app icon. Faithfully preserve supplied logo identity.

Фактический результат генерации — квадратные непрозрачные мастера; прозрачные
углы из первого запроса модель не воспроизвела. Экспорт сохраняет их фон.
