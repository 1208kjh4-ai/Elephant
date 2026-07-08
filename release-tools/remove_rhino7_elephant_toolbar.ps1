param(
    [switch]$Apply,
    [switch]$RemoveScripts
)

$ErrorActionPreference = "Stop"

$rhino7Root = Join-Path $env:APPDATA "McNeel\Rhinoceros\7.0"
$uiRoot = Join-Path $rhino7Root "UI"
$pluginToolbar = Join-Path $uiRoot "Plug-ins\ElephantToolsR7.rui"
$pluginToolbarBackups = @(
    (Join-Path $uiRoot "Plug-ins\ElephantToolsR7.rui.rui_bak"),
    (Join-Path $uiRoot "Plug-ins\ElephantToolsR7.rui_bak")
)
$defaultRui = Join-Path $uiRoot "default.rui"
$defaultRuiBackup = Join-Path $uiRoot "default.rui.rui_bak"
$scriptsFolder = Join-Path $rhino7Root "scripts\Elephant"
$backupRoot = Join-Path $rhino7Root ("ElephantToolbarBackup_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

function Get-NodeText {
    param($Node)

    if ($null -eq $Node) {
        return ""
    }
    return [string]$Node.InnerText
}

function Test-ElephantText {
    param($Node)

    $text = Get-NodeText $Node
    return ($text -match "Elephant Tools_R7|ElephantToolsR7|Elephant/commands|Elephant/system")
}

function Remove-XmlNode {
    param($Node)

    if ($null -ne $Node -and $null -ne $Node.ParentNode) {
        [void]$Node.ParentNode.RemoveChild($Node)
        return $true
    }
    return $false
}

function Copy-ToBackup {
    param(
        [string]$Path,
        [string]$BackupDirectory
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $name = Split-Path -Leaf $Path
    $destination = Join-Path $BackupDirectory $name
    Copy-Item -LiteralPath $Path -Destination $destination -Recurse -Force
}

Write-Host "Rhino 7 Elephant toolbar cleanup"
Write-Host "Rhino 7 root: $rhino7Root"
Write-Host ""

if (-not $Apply) {
    Write-Host "Dry-run mode. No files will be changed."
    Write-Host "Run again with -Apply to back up and remove Rhino 7 Elephant toolbar data."
    Write-Host "Add -RemoveScripts only if you also want to remove the Rhino 7 scripts\Elephant folder."
    Write-Host ""
}

$fileTargets = @($pluginToolbar) + $pluginToolbarBackups
if ($RemoveScripts) {
    $fileTargets += $scriptsFolder
}

$existingFileTargets = @()
foreach ($path in $fileTargets) {
    if (Test-Path -LiteralPath $path) {
        $existingFileTargets += (Get-Item -LiteralPath $path -Force)
        Write-Host ("FOUND FILE/FOLDER: {0}" -f $path)
    }
    else {
        Write-Host ("MISSING FILE/FOLDER: {0}" -f $path)
    }
}

$ruiChanges = [ordered]@{
    Toolbars = 0
    ToolbarGroupItems = 0
    Macros = 0
}

if (Test-Path -LiteralPath $defaultRui) {
    [xml]$doc = Get-Content -LiteralPath $defaultRui -Encoding UTF8 -Raw

    $toolbarIds = New-Object "System.Collections.Generic.HashSet[string]"
    $macroIds = New-Object "System.Collections.Generic.HashSet[string]"

    foreach ($toolbar in @($doc.SelectNodes("//tool_bar"))) {
        if (Test-ElephantText $toolbar) {
            $guid = [string]$toolbar.guid
            if ($guid) {
                [void]$toolbarIds.Add($guid)
            }

            foreach ($macroIdNode in @($toolbar.SelectNodes(".//left_macro_id|.//right_macro_id|.//macro_id"))) {
                $macroId = (Get-NodeText $macroIdNode).Trim()
                if ($macroId) {
                    [void]$macroIds.Add($macroId)
                }
            }
        }
    }

    foreach ($groupItem in @($doc.SelectNodes("//tool_bar_group_item"))) {
        $toolBarId = (Get-NodeText $groupItem.SelectSingleNode("./tool_bar_id")).Trim()
        if (($toolBarId -and $toolbarIds.Contains($toolBarId)) -or (Test-ElephantText $groupItem)) {
            $ruiChanges.ToolbarGroupItems += 1
            if ($Apply) {
                [void](Remove-XmlNode $groupItem)
            }
        }
    }

    foreach ($toolbar in @($doc.SelectNodes("//tool_bar"))) {
        $guid = [string]$toolbar.guid
        if (($guid -and $toolbarIds.Contains($guid)) -or (Test-ElephantText $toolbar)) {
            $ruiChanges.Toolbars += 1
            if ($Apply) {
                [void](Remove-XmlNode $toolbar)
            }
        }
    }

    foreach ($macro in @($doc.SelectNodes("//macro_item"))) {
        $guid = [string]$macro.guid
        if (($guid -and $macroIds.Contains($guid)) -or (Test-ElephantText $macro)) {
            $ruiChanges.Macros += 1
            if ($Apply) {
                [void](Remove-XmlNode $macro)
            }
        }
    }

    Write-Host ""
    Write-Host "default.rui Elephant entries:"
    Write-Host ("  Toolbar group items: {0}" -f $ruiChanges.ToolbarGroupItems)
    Write-Host ("  Toolbars:            {0}" -f $ruiChanges.Toolbars)
    Write-Host ("  Macros:              {0}" -f $ruiChanges.Macros)
}
else {
    Write-Host ""
    Write-Host ("MISSING FILE/FOLDER: {0}" -f $defaultRui)
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "No changes were made."
    exit 0
}

New-Item -ItemType Directory -Path $backupRoot | Out-Null
Write-Host ""
Write-Host "Backup folder: $backupRoot"

foreach ($item in $existingFileTargets) {
    Copy-ToBackup -Path $item.FullName -BackupDirectory $backupRoot
    Remove-Item -LiteralPath $item.FullName -Recurse -Force
    Write-Host ("REMOVED FILE/FOLDER: {0}" -f $item.FullName)
}

if (Test-Path -LiteralPath $defaultRui) {
    Copy-ToBackup -Path $defaultRui -BackupDirectory $backupRoot
    if (Test-Path -LiteralPath $defaultRuiBackup) {
        Copy-ToBackup -Path $defaultRuiBackup -BackupDirectory $backupRoot
    }

    $doc.Save($defaultRui)
    Write-Host ("UPDATED FILE: {0}" -f $defaultRui)
}

Write-Host ""
Write-Host "Done. Restart Rhino 7, then load the current ElephantToolsR7.rui file again."
Write-Host "If something looks wrong, restore files from the backup folder above."
