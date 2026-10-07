param(
    [string]$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')),
    [switch]$Apply,
    [switch]$OldReleases
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath $Root).Path
$rootPrefix = $projectRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'backend') -PathType Container) -or
    !(Test-Path -LiteralPath (Join-Path $projectRoot 'VERSION.json') -PathType Leaf)) {
    throw 'Root must be a ScottAI project directory.'
}
if ((Get-Item -LiteralPath $projectRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Cleanup does not follow junctions or symbolic links.'
}

function Assert-ProjectPath([string]$Target) {
    $absolute = [IO.Path]::GetFullPath($Target)
    if (!$absolute.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target is outside the project: $absolute"
    }
    return $absolute
}

function Get-SafeTreeStats([string]$Directory, [bool]$BytecodeOnly) {
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($Directory)
    $count = 0
    $bytes = [long]0
    while ($pending.Count) {
        $current = $pending.Pop()
        foreach ($item in Get-ChildItem -LiteralPath $current -Force) {
            $null = Assert-ProjectPath $item.FullName
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $null }
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            else {
                if ($BytecodeOnly -and $item.Extension -notin @('.pyc', '.pyo')) { return $null }
                $count++
                $bytes += $item.Length
            }
        }
    }
    return [PSCustomObject]@{ Files = $count; Bytes = $bytes }
}

$skip = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@('.git', '.agents', '.codex', '.aws', '.claude', '.vscode', '.venv', 'venv', 'env',
  'node_modules', 'models', 'data', 'audio_cache', 'reports', 'logs', '.cache',
  'release', 'bin', 'obj', 'dist', 'dist-qt', 'dist-linux', 'dist-macos') |
    ForEach-Object { $null = $skip.Add($_) }
$targets = [Collections.Generic.List[object]]::new()
$pending = [Collections.Generic.Stack[string]]::new()
$pending.Push($projectRoot)
while ($pending.Count) {
    foreach ($item in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        $absolute = Assert-ProjectPath $item.FullName
        if ($item.PSIsContainer) {
            if ($skip.Contains($item.Name) -or $item.Name.StartsWith('build', [StringComparison]::OrdinalIgnoreCase)) { continue }
            if ($item.Name -in @('__pycache__', '.pytest_cache', '.ruff_cache')) {
                $stats = Get-SafeTreeStats $absolute ($item.Name -eq '__pycache__')
                if ($null -ne $stats) {
                    $targets.Add([PSCustomObject]@{ Path=$absolute; Kind=$item.Name; Files=$stats.Files; Bytes=$stats.Bytes; Directory=$true; Deleted=$false })
                }
            } else { $pending.Push($absolute) }
        } elseif ($item.Name -match '\.csproj\.SdkResolver\.-?\d+\.proj\.Backup\.tmp$') {
            $targets.Add([PSCustomObject]@{ Path=$absolute; Kind='SDK temporary'; Files=1; Bytes=$item.Length; Directory=$false; Deleted=$false })
        }
    }
}

if ($OldReleases) {
    $currentVersion = [Version](Get-Content -LiteralPath (Join-Path $projectRoot 'VERSION.json') -Raw | ConvertFrom-Json).version
    $releaseRoot = Join-Path $projectRoot 'installer/release'
    if (Test-Path -LiteralPath $releaseRoot -PathType Container) {
        if ((Get-Item -LiteralPath $releaseRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Release directory is a link.' }
        foreach ($item in Get-ChildItem -LiteralPath $releaseRoot -File) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            if ($item.Name -match '^ScottAI-(?<version>\d+\.\d+\.\d+)-(?<variant>setup\.exe|Qt-setup\.exe|linux-x64\.tar\.gz|macos-(?:arm64|x86_64)\.(?:zip|dmg))$') {
                $oldVersion = [Version]$Matches.version
                $replacement = Join-Path $releaseRoot ('ScottAI-' + $currentVersion + '-' + $Matches.variant)
                if ($oldVersion -lt $currentVersion -and (Test-Path -LiteralPath $replacement -PathType Leaf) -and
                    (Get-Item -LiteralPath $replacement).Length -gt 0) {
                    $targets.Add([PSCustomObject]@{ Path=(Assert-ProjectPath $item.FullName); Kind='Old release'; Files=1; Bytes=$item.Length; Directory=$false; Deleted=$false })
                }
            }
        }
    }
}

$reportRoot = Join-Path $projectRoot 'reports'
$null = New-Item -ItemType Directory -Path $reportRoot -Force
$reportPath = Join-Path $reportRoot 'project-cleanup.json'
$report = [PSCustomObject]@{ Root=$projectRoot; Applied=[bool]$Apply; Created=(Get-Date).ToString('o'); Targets=@($targets.ToArray()) }
function Save-Report {
    [IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
}
Save-Report
if ($Apply) {
    foreach ($target in $targets) {
        $absolute = Assert-ProjectPath $target.Path
        $item = Get-Item -LiteralPath $absolute -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Target became a link.' }
        if ($target.Directory) {
            $stats = Get-SafeTreeStats $absolute ($item.Name -eq '__pycache__')
            if ($null -eq $stats) { throw "Target contains a link or unexpected files: $absolute" }
            Remove-Item -LiteralPath $absolute -Recurse -Force
        } else { Remove-Item -LiteralPath $absolute -Force }
        $target.Deleted = !(Test-Path -LiteralPath $absolute)
        Save-Report
    }
}
$totalBytes = ($targets | Measure-Object -Property Bytes -Sum).Sum
$totalFiles = ($targets | Measure-Object -Property Files -Sum).Sum
$targets | Select-Object Kind, @{n='Path';e={$_.Path.Substring($rootPrefix.Length)}}, Files, @{n='MiB';e={[math]::Round($_.Bytes / 1MB, 2)}}, Deleted | Format-Table -AutoSize
Write-Output ("{0}: {1} targets, {2} files, {3:N2} MiB. Manifest: {4}" -f $(if ($Apply) {'Removed'} else {'Preview'}), $targets.Count, $totalFiles, ($totalBytes / 1MB), $reportPath)
