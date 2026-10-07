# Export the approved icon masters. Run from any directory on Windows:
# powershell -ExecutionPolicy Bypass -File installer/export_icons.ps1
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$projectRoot = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $projectRoot 'ScottAI_avalonia/Assets'
$brand = Join-Path $projectRoot 'docs/brand'
$sizes = @(16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024)

function Export-Png($source, [int]$size, [string]$path) {
    $bitmap = New-Object System.Drawing.Bitmap($size, $size)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CompositingQuality = 'HighQuality'
        $graphics.InterpolationMode = 'HighQualityBicubic'
        $graphics.PixelOffsetMode = 'HighQuality'
        $attributes = New-Object System.Drawing.Imaging.ImageAttributes
        try {
            $attributes.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
            $rect = New-Object System.Drawing.Rectangle(0, 0, $size, $size)
            $graphics.DrawImage($source, $rect, 0, 0, $source.Width, $source.Height,
                [System.Drawing.GraphicsUnit]::Pixel, $attributes)
            $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $attributes.Dispose() }
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function Export-Ico([string]$path, [string]$prefix) {
    # Each PNG is rendered directly from the master, never from another size.
    $iconSizes = @($sizes | Where-Object { $_ -le 256 })
    $stream = [System.IO.File]::Create($path)
    $writer = New-Object System.IO.BinaryWriter($stream)
    try {
        $writer.Write([uint16]0)
        $writer.Write([uint16]1)
        $writer.Write([uint16]$iconSizes.Count)
        $offset = 6 + 16 * $iconSizes.Count
        foreach ($size in $iconSizes) {
            $bytes = [System.IO.File]::ReadAllBytes((Join-Path $assets "$prefix-$size.png"))
            $dimension = if ($size -eq 256) { 0 } else { $size }
            $writer.Write([byte]$dimension)
            $writer.Write([byte]$dimension)
            $writer.Write([byte]0)
            $writer.Write([byte]0)
            $writer.Write([uint16]1)
            $writer.Write([uint16]32)
            $writer.Write([uint32]$bytes.Length)
            $writer.Write([uint32]$offset)
            $offset += $bytes.Length
        }
        foreach ($size in $iconSizes) {
            $writer.Write([System.IO.File]::ReadAllBytes((Join-Path $assets "$prefix-$size.png")))
        }
    } finally { $writer.Dispose() }
}

foreach ($variant in @('', '-light')) {
    $source = [System.Drawing.Image]::FromFile((Join-Path $brand "scott-icon$variant-master.png"))
    try {
        foreach ($size in $sizes) {
            Export-Png $source $size (Join-Path $assets "icon$variant-$size.png")
        }
        Export-Png $source 512 (Join-Path $assets "scott-logo$variant.png")
    } finally { $source.Dispose() }
    Export-Ico (Join-Path $assets "scott$variant.ico") "icon$variant"
}

Copy-Item (Join-Path $assets 'scott.ico') (Join-Path $projectRoot 'ScottAI_mobile/ScottAI.Mobile/Assets/scott.ico')
Copy-Item (Join-Path $assets 'icon-512.png') (Join-Path $projectRoot 'ScottAI_mobile/ScottAI.Mobile/Assets/Icon.png')
Copy-Item (Join-Path $assets 'icon-512.png') (Join-Path $projectRoot 'ScottAI_mobile/ScottAI.Mobile.Android/Icon.png')
Write-Output 'Exported both icon variants, launcher logos and mobile icons.'
