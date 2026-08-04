param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
$distDir = Join-Path $projectRoot "dist"
$stageRoot = Join-Path $distDir "_stage"
$packageRoot = Join-Path $stageRoot "Elephant"
$zipPath = Join-Path $distDir ("Elephant-v{0}.zip" -f $Version)

function Assert-InProject {
    param([string]$Path)

    $resolvedProject = [System.IO.Path]::GetFullPath($projectRoot)
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $resolvedPath.StartsWith($resolvedProject, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside project root: $resolvedPath"
    }
}

function Copy-RequiredItem {
    param(
        [string]$RelativePath
    )

    $source = Join-Path $projectRoot $RelativePath
    $target = Join-Path $packageRoot $RelativePath

    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing required release item: $RelativePath"
    }

    $parent = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }

    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
}

function Remove-ReleaseClutter {
    param(
        [string]$Root
    )

    $excludedFilePatterns = @("*.pyc", "*.pyo", "*.zip", "*.rhl", "*.3dmbak")
    foreach ($pattern in $excludedFilePatterns) {
        Get-ChildItem -LiteralPath $Root -Recurse -Force -File -Filter $pattern |
            Remove-Item -Force
    }

    Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -Filter "__pycache__" |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force
}

Assert-InProject $distDir
Assert-InProject $stageRoot

if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}

if (-not (Test-Path -LiteralPath $distDir)) {
    New-Item -ItemType Directory -Path $distDir | Out-Null
}

New-Item -ItemType Directory -Path $packageRoot | Out-Null

$requiredItems = @(
    "commands",
    "icons",
    "ElephantTools.rhc",
    "ElephantToolsR7.rui",
    "Source.3dm",
    "korroadfont.3dm",
    "AuditoriumSeat.3dm",
    "RoadMarkDB.json",
    "shapefile.py",
    "LICENSE",
    "LICENSE-pyshp.txt",
    "README.md"
)

foreach ($item in $requiredItems) {
    Copy-RequiredItem $item
}

Remove-ReleaseClutter $packageRoot

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal

Remove-Item -LiteralPath $stageRoot -Recurse -Force

Write-Host ("Created release package: {0}" -f $zipPath)
