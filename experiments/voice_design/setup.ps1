param(
    [string]$Python = '',
    [string]$TorchAudioVersion = '2.9.1+cu126',
    [string]$TorchIndex = 'https://download.pytorch.org/whl/cu126'
)
$ErrorActionPreference = 'Stop'
if (!$Python) {
    $Python = (& py -3.13 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    if ($LASTEXITCODE -or !$Python) { throw 'Python 3.13 not found.' }
}
$environmentPath = Join-Path $PSScriptRoot '.venv'
$environmentPython = Join-Path $environmentPath 'Scripts/python.exe'
if (!(Test-Path -LiteralPath $environmentPython)) {
    & $Python -m venv --system-site-packages $environmentPath
    if ($LASTEXITCODE) { throw 'Could not create the voice experiment environment.' }
}
& $environmentPython -m pip install --disable-pip-version-check --no-cache-dir "torchaudio==$TorchAudioVersion" --index-url $TorchIndex
if ($LASTEXITCODE) { throw 'Could not install matching TorchAudio.' }
& $environmentPython -m pip install --disable-pip-version-check --no-cache-dir -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE) { throw 'Could not install Qwen TTS dependencies.' }
& $environmentPython -m pip check
if ($LASTEXITCODE) { throw 'Dependency check failed.' }
Write-Output "Ready: $environmentPython"
