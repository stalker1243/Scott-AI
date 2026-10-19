param(
    [string]$CompilerRoot = 'C:\msys64\ucrt64',
    [string]$CMake = 'C:\Qt\Tools\CMake_64\bin\cmake.exe',
    [string]$NinjaRoot = 'C:\Qt\Tools\Ninja',
    [string]$VulkanPrefix = '',
    [string]$BlasPrefix = '',
    [string]$BuildName = 'worker-cpu'
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$reportRoot = Join-Path $repoRoot 'reports/whisper-cpp'
$source = Join-Path $reportRoot 'upstream'
$build = [IO.Path]::GetFullPath((Join-Path $reportRoot $BuildName))
if (-not $build.StartsWith($reportRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw 'BuildName must stay inside reports/whisper-cpp'
}
New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
$commit = 'd1be6fde11ac6e0407606b4e42fe72d34add8037'
if (-not (Test-Path -LiteralPath $source)) {
    git clone --depth 1 --branch v1.9.5 https://github.com/ggml-org/whisper.cpp.git $source
    if ($LASTEXITCODE -ne 0) { throw 'Source download failed' }
}
$actual = git -C $source rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actual.Trim() -ne $commit) {
    throw 'Unexpected whisper.cpp revision; existing checkout was preserved'
}
$env:PATH = (Join-Path $CompilerRoot 'bin') + ';' + $NinjaRoot + ';' + $env:PATH
$arguments = @('-S', $PSScriptRoot, '-B', $build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
    "-DCMAKE_C_COMPILER=$CompilerRoot/bin/gcc.exe", "-DCMAKE_CXX_COMPILER=$CompilerRoot/bin/g++.exe",
    "-DWHISPER_SOURCE=$source", '-DGGML_VULKAN=OFF', '-DGGML_BLAS=OFF')
if ($VulkanPrefix) {
    $VulkanPrefix = [IO.Path]::GetFullPath($VulkanPrefix)
    $env:PATH = (Join-Path $VulkanPrefix 'bin') + ';' + $env:PATH
    $arguments += @('-DGGML_VULKAN=ON', "-DCMAKE_PREFIX_PATH=$VulkanPrefix",
        "-DVulkan_INCLUDE_DIR=$VulkanPrefix/include",
        "-DVulkan_LIBRARY=$VulkanPrefix/lib/libvulkan-1.dll.a",
        "-DVulkan_GLSLC_EXECUTABLE=$VulkanPrefix/bin/glslc.exe")
}
if ($BlasPrefix) {
    $BlasPrefix = [IO.Path]::GetFullPath($BlasPrefix)
    if (-not (Test-Path -LiteralPath (Join-Path $BlasPrefix 'include/openblas/cblas.h'))) {
        throw 'OpenBLAS headers not found'
    }
    $env:PATH = (Join-Path $BlasPrefix 'bin') + ';' + $env:PATH
    $arguments += @('-DGGML_BLAS=ON', '-DGGML_BLAS_VENDOR=OpenBLAS',
        "-DBLAS_INCLUDE_DIRS=$BlasPrefix/include/openblas",
        "-DBLAS_openblas_LIBRARY=$BlasPrefix/lib/libopenblas.dll.a")
}
& $CMake @arguments
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
& $CMake --build $build --target ScottWhisperBench --parallel 8
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
