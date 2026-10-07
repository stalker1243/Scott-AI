param(
    [string]$InstallerPath = (Join-Path $PSScriptRoot 'release/ScottAI-1.2.0-Qt-setup.exe'),
    [string]$Screenshot = (Join-Path $PSScriptRoot '../reports/installer-welcome.png')
)
$ErrorActionPreference = 'Stop'
$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
if (!$InstallerPath.StartsWith((Join-Path $PSScriptRoot 'release'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Preview only installers built in installer/release' }
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ScottInstallerPreview {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr dc, uint flags);
}
'@
$preview = Start-Process -FilePath $InstallerPath -ArgumentList '/LANG=russian' -WindowStyle Normal -PassThru
$owner = $preview
try {
    # Inno's loader creates the wizard as a child process.
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $owner.Refresh()
        if ($owner.MainWindowHandle -ne [IntPtr]::Zero) { break }
        $child = Get-CimInstance Win32_Process -Filter ("ParentProcessId=" + $preview.Id) | Where-Object Name -Like '*.tmp' | Select-Object -First 1
        if ($child) { $owner = Get-Process -Id $child.ProcessId }
        Start-Sleep -Milliseconds 250
    }
    if ($owner.MainWindowHandle -eq [IntPtr]::Zero) { throw 'Installer wizard not found' }
    Start-Sleep -Milliseconds 500
    $rect = New-Object ScottInstallerPreview+Rect
    if (![ScottInstallerPreview]::GetWindowRect($owner.MainWindowHandle, [ref]$rect)) { throw 'Cannot read wizard bounds' }
    $bitmap = New-Object Drawing.Bitmap(($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top))
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $dc = $graphics.GetHdc()
    try { if (![ScottInstallerPreview]::PrintWindow($owner.MainWindowHandle, $dc, 2)) { throw 'Cannot render wizard' } }
    finally { $graphics.ReleaseHdc($dc) }
    $bitmap.Save($Screenshot, [Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose(); $bitmap.Dispose()
    Write-Output $Screenshot
} finally {
    # Stop only the loader and wizard created here, while still on the welcome page.
    if ($owner.Id -ne $preview.Id) { Stop-Process -Id $owner.Id -ErrorAction SilentlyContinue }
    Stop-Process -Id $preview.Id -ErrorAction SilentlyContinue
}
