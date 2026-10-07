param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'assets'))
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
# Native branding artwork, exported at 200% for crisp wizard scaling.
function Export-WizardImage([bool]$Small) {
    $width = if ($Small) { 110 } else { 328 }
    $height = if ($Small) { 110 } else { 628 }
    $bitmap = New-Object Drawing.Bitmap($width, $height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $bounds = New-Object Drawing.Rectangle(0, 0, $width, $height)
    $gradient = New-Object Drawing.Drawing2D.LinearGradientBrush($bounds, [Drawing.ColorTranslator]::FromHtml('#142239'), [Drawing.ColorTranslator]::FromHtml('#090d16'), 70)
    $graphics.FillRectangle($gradient, $bounds)
    $pen = New-Object Drawing.Pen([Drawing.ColorTranslator]::FromHtml('#293d5c'), 1)
    for ($y = 16; $y -lt $height; $y += 32) { $graphics.DrawLine($pen, 0, $y, $width, $y) }
    $icon = [Drawing.Image]::FromFile((Join-Path $PSScriptRoot '../ScottAI_avalonia/Assets/icon-256.png'))
    if ($Small) {
        $graphics.DrawImage($icon, (New-Object Drawing.Rectangle(15, 15, 80, 80)))
    } else {
        $graphics.DrawImage($icon, (New-Object Drawing.Rectangle(36, 40, 140, 140)))
        $white = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#f2f5fc'))
        $muted = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#9dacc6'))
        $accent = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#75a0ff'))
        $titleFont = New-Object Drawing.Font('Segoe UI', 27, [Drawing.FontStyle]::Bold, [Drawing.GraphicsUnit]::Pixel)
        $bodyFont = New-Object Drawing.Font('Segoe UI', 17, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
        $smallFont = New-Object Drawing.Font('Segoe UI', 13, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
        $graphics.DrawString('Scott AI', $titleFont, $white, 36, 200)
        $graphics.DrawString('Ваш личный ассистент', $bodyFont, $muted, 36, 247)
        $graphics.FillRectangle($accent, 36, 299, 46, 3)
        $graphics.DrawString('ДИАЛОГ И ПАМЯТЬ', $smallFont, $accent, 36, 350)
        $graphics.DrawString('ГОЛОС И КОМАНДЫ', $smallFont, $accent, 36, 388)
        $graphics.DrawString('МОДЕЛИ НА ВЫБОР', $smallFont, $accent, 36, 426)
        $graphics.DrawString('Настройте под себя.', $bodyFont, $white, 36, 540)
        $graphics.DrawString('Начните с одного вопроса.', $smallFont, $muted, 36, 573)
        $white.Dispose(); $muted.Dispose(); $accent.Dispose()
        $titleFont.Dispose(); $bodyFont.Dispose(); $smallFont.Dispose()
    }
    $name = if ($Small) { 'wizard-small.bmp' } else { 'wizard-sidebar.bmp' }
    $bitmap.Save((Join-Path $OutputDirectory $name), [Drawing.Imaging.ImageFormat]::Bmp)
    $graphics.Dispose(); $bitmap.Dispose(); $gradient.Dispose(); $pen.Dispose(); $icon.Dispose()
}
Export-WizardImage $false
Export-WizardImage $true
