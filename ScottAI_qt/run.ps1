param(
    [string]$QtRoot = 'C:\Qt\6.11.2\mingw_64',
    [string]$CompilerRoot = 'C:\Qt\Tools\mingw1310_64',
    [string]$Python = '',
    [ValidateSet('home','chat','system','appearance','memory','settings','profile','actions','protocols','models')]
    [string]$Tab = 'home',
    [ValidateSet('classic','glass','terminal-pro')]
    [string]$Style = ''
)
$ErrorActionPreference = 'Stop'
$appPath = Join-Path $PSScriptRoot 'build/ScottAIQt.exe'
if (!(Test-Path -LiteralPath $appPath)) { throw 'Run build.ps1 first.' }
if (!$Python) {
    $Python = (& py -3.13 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    if ($LASTEXITCODE -or !$Python) { throw 'Python 3.13 not found; provide -Python with its executable path.' }
}
$previousPath = $env:PATH
try {
    $env:PATH = "$CompilerRoot/bin;$QtRoot/bin;" + $env:PATH
    # This is a GUI executable: no console is created. Show its interactive window.
    $arguments = @('--start-backend', '--tab', $Tab, '--python', ('"' + $Python + '"'), '--backend-dir', ('"' + (Join-Path $PSScriptRoot '../backend') + '"'))
    if ($Style) { $arguments += @('--surface-style', $Style) }
    Start-Process -FilePath $appPath -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Normal -PassThru |
        Select-Object Id,ProcessName
} finally { $env:PATH = $previousPath }
