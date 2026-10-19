param(
    [string]$Python = '',
    [string]$TorchAudioVersion = '2.11.0+cu126',
    [string]$TorchIndex = 'https://download.pytorch.org/whl/cu126',
    [string]$EnvironmentDirectory = '.venv'
)
$ErrorActionPreference = 'Stop'
$savedEnvironment = @{}
foreach ($item in @(Get-ChildItem Env:)) {
    if ($item.Name -match '(^PIP_|_API_KEY$|_TOKEN$|^AWS_ACCESS_KEY_ID$|^AWS_SECRET_ACCESS_KEY$|^PYTHONPATH$|^PYTHONHOME$|^VIRTUAL_ENV$|^PYTHONNOUSERSITE$)') {
        $savedEnvironment[$item.Name] = $item.Value
        Remove-Item -LiteralPath ("Env:" + $item.Name)
    }
}
try {
$env:PIP_CONFIG_FILE = 'NUL'
$env:PYTHONNOUSERSITE = '1'
if (!$Python) {
    $Python = (& py -3.13 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    if ($LASTEXITCODE -or !$Python) { throw 'Python 3.13 not found.' }
}
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$sdkPath = Join-Path $projectRoot 'backend\scott_voice_sdk.py'
$sdkProbe = @'
import json,runpy,sys
profile=runpy.run_path(sys.argv[1])
print(json.dumps({name:profile[name] for name in ('TORCH','TORCHAUDIO','WHEEL','WHEEL_SHA256')}))
'@
$sdkJson = ($sdkProbe | & $Python -I - $sdkPath | Select-Object -Last 1)
if ($LASTEXITCODE) { throw 'Could not read the qualified Scott Voice SDK profile.' }
$sdk = $sdkJson | ConvertFrom-Json
if ($TorchAudioVersion -ne $sdk.TORCHAUDIO -or $TorchIndex -ne 'https://download.pytorch.org/whl/cu126') {
    throw 'This script supports the qualified Windows CUDA SDK profile only.'
}
$wheel = Join-Path $projectRoot $sdk.WHEEL
if ((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sdk.WHEEL_SHA256) {
    throw 'The Scott Voice compatibility wheel checksum does not match.'
}
$environmentPath = if ([IO.Path]::IsPathRooted($EnvironmentDirectory)) { $EnvironmentDirectory } else { Join-Path $PSScriptRoot $EnvironmentDirectory }
$environmentPython = Join-Path $environmentPath 'Scripts/python.exe'
if (Test-Path -LiteralPath $environmentPython) {
    $settings = Get-Content -LiteralPath (Join-Path $environmentPath 'pyvenv.cfg') -Raw
    if ($settings -notmatch '(?im)^include-system-site-packages\s*=\s*false\s*$') {
        throw 'The existing environment uses global packages and was preserved. Choose a new -EnvironmentDirectory.'
    }
}
if (!(Test-Path -LiteralPath $environmentPython)) {
    & $Python -m venv $environmentPath
    if ($LASTEXITCODE) { throw 'Could not create the voice experiment environment.' }
}
& $environmentPython -m pip install --disable-pip-version-check --no-cache-dir "torch==$($sdk.TORCH)" "torchaudio==$TorchAudioVersion" --index-url $TorchIndex
if ($LASTEXITCODE) { throw 'Could not install the qualified PyTorch/TorchAudio pair.' }
& $environmentPython -m pip install --disable-pip-version-check --no-cache-dir $wheel -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE) { throw 'Could not install Qwen TTS dependencies.' }
& $environmentPython -m pip check
if ($LASTEXITCODE) { throw 'Dependency check failed.' }
Write-Output "Ready: $environmentPython"
} finally {
    Remove-Item Env:PIP_CONFIG_FILE -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue
    foreach ($name in $savedEnvironment.Keys) {
        Set-Item -LiteralPath ("Env:" + $name) -Value $savedEnvironment[$name]
    }
}
