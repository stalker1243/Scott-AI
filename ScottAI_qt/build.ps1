param(
    [string]$QtRoot = 'C:\Qt\6.11.2\mingw_64',
    [string]$CompilerRoot = 'C:\Qt\Tools\mingw1310_64',
    [string]$Ninja = 'C:\Qt\Tools\Ninja\ninja.exe',
    [switch]$Test
)
$ErrorActionPreference = 'Stop'
foreach ($tool in @("$QtRoot/bin/qmake.exe", "$CompilerRoot/bin/g++.exe", $Ninja)) {
    if (!(Test-Path -LiteralPath $tool)) { throw "Tool not found: $tool" }
}
$previousPath = $env:PATH
try {
    $env:PATH = "$CompilerRoot/bin;$QtRoot/bin;" + $env:PATH
    & "$CompilerRoot/bin/g++.exe" --version | Select-Object -First 1
    & "$QtRoot/bin/qmake.exe" -query QT_VERSION
    & cmake -S $PSScriptRoot -B "$PSScriptRoot/build" -G Ninja `
        "-DCMAKE_MAKE_PROGRAM=$Ninja" "-DCMAKE_CXX_COMPILER=$CompilerRoot/bin/g++.exe" `
        "-DCMAKE_PREFIX_PATH=$QtRoot" -DCMAKE_BUILD_TYPE=Release
    if ($LASTEXITCODE) { throw 'CMake configure failed' }
    & cmake --build "$PSScriptRoot/build" --parallel 4
    if ($LASTEXITCODE) { throw 'Build failed' }
    if ($Test) {
        & ctest --test-dir "$PSScriptRoot/build" --output-on-failure
        if ($LASTEXITCODE) { throw 'Tests failed' }
    }
} finally { $env:PATH = $previousPath }
