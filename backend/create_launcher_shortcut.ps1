param(
  [string]$LauncherBat = "",
  [string]$ShortcutName = "Scott Launcher",
  [switch]$DesktopShortcut,
  [switch]$StartMenuShortcut
)

if (-not $DesktopShortcut -and -not $StartMenuShortcut) {
  $DesktopShortcut = $true
  $StartMenuShortcut = $true
}

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($LauncherBat -eq "") {
  $exePath = Join-Path $baseDir "dist\ScottLauncher.exe"
  if (Test-Path $exePath) {
    $LauncherBat = $exePath
  } else {
    $LauncherBat = Join-Path $baseDir "launcher.bat"
  }
}

if (-not (Test-Path $LauncherBat)) {
  Write-Host "Launcher BAT not found: $LauncherBat" -ForegroundColor Red
  exit 1
}

function New-ShortcutFile {
  param(
    [string]$DestinationDir,
    [string]$TargetPath,
    [string]$Name
  )
  if (-not (Test-Path $DestinationDir)) {
    New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
  }
  $linkPath = Join-Path $DestinationDir ($Name + ".lnk")
  $WshShell = New-Object -ComObject WScript.Shell
  $Shortcut = $WshShell.CreateShortcut($linkPath)
  $Shortcut.TargetPath = $TargetPath
  $Shortcut.WorkingDirectory = Split-Path -Parent $TargetPath

  $AssetsDir = Join-Path $baseDir "assets"
  $IcoPath = Join-Path $AssetsDir "maltruand.ico"
  if (Test-Path $IcoPath) {
    $Shortcut.IconLocation = $IcoPath
  } else {
    $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll, 167"
  }
  $Shortcut.Save()
  Write-Host "✅ Shortcut created: $linkPath"
}

if ($DesktopShortcut) {
  $desktop = [Environment]::GetFolderPath("Desktop")
  New-ShortcutFile -DestinationDir $desktop -TargetPath $LauncherBat -Name $ShortcutName
}

if ($StartMenuShortcut) {
  $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
  New-ShortcutFile -DestinationDir $startMenu -TargetPath $LauncherBat -Name $ShortcutName
}


