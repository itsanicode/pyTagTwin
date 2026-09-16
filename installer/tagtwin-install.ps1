# Tag Twin - one-click installer / uninstaller for the pyRevit extension.
# Copies the extension into the pyRevit user extensions folder. No administrator
# rights required, and nothing outside your user profile is touched.
#
# Most people should install through pyRevit itself instead:
#   pyRevit > Extensions > Git URL: https://github.com/itsanicode/pyTagTwin.git
# This script is for anyone who would rather not use the Extension Manager.
param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$source        = $PSScriptRoot
$extensionName = 'pyTagTwin.extension'
$extensionsDir = Join-Path $env:APPDATA 'pyRevit\Extensions'
$target        = Join-Path $extensionsDir $extensionName

# What Revit actually loads. The repo root is the extension bundle, so a clone
# holds these alongside tests/ and tools/, which are not worth installing.
$bundleContent = @('extension.json', 'lib', 'Tag Twin.tab')

Write-Host ''
Write-Host '  ============================================' -ForegroundColor Cyan
if ($Uninstall) {
    Write-Host '   Tag Twin - Uninstall'                    -ForegroundColor Cyan
} else {
    Write-Host '   Tag Twin - Install'                      -ForegroundColor Cyan
}
Write-Host '  ============================================' -ForegroundColor Cyan
Write-Host ''

if ($Uninstall) {
    if (Test-Path $target) {
        Remove-Item $target -Recurse -Force
        Write-Host "   Removed $target" -ForegroundColor Green
    } else {
        Write-Host '   Tag Twin was not installed - nothing to remove.' -ForegroundColor DarkGray
    }
    Write-Host ''
    Write-Host '   Restart Revit, or click pyRevit > Reload, to drop the tab.'
    Write-Host ''
    return
}

# Two ways this script gets run: from the extracted zip, where a ready-made
# pyTagTwin.extension sits next to it, or from a clone, where the repo root one
# folder up is itself the bundle.
$packaged = Join-Path $source $extensionName
$clone    = Split-Path $source -Parent

if (Test-Path (Join-Path $packaged 'lib\tagtwin')) {
    $mode = 'packaged'
} elseif (Test-Path (Join-Path $clone 'lib\tagtwin')) {
    $mode = 'clone'
} else {
    Write-Host "   Could not find the Tag Twin extension near this installer." -ForegroundColor Red
    Write-Host ''
    Write-Host '   If you downloaded the zip, extract the WHOLE thing first' -ForegroundColor Red
    Write-Host '   (right-click the zip -> Extract All...) and run the installer' -ForegroundColor Red
    Write-Host '   again from inside the extracted folder.' -ForegroundColor Red
    Write-Host ''
    return
}

if (-not (Test-Path $extensionsDir)) {
    Write-Host '   pyRevit does not appear to be installed for this user:' -ForegroundColor Yellow
    Write-Host "   $extensionsDir does not exist." -ForegroundColor Yellow
    Write-Host ''
    Write-Host '   Tag Twin is a pyRevit extension, so install pyRevit first from' -ForegroundColor Yellow
    Write-Host '   https://github.com/pyrevitlabs/pyRevit/releases - then run this again.' -ForegroundColor Yellow
    Write-Host ''
    $answer = Read-Host '   Create the folder and install anyway? (y/N)'
    if ($answer -notmatch '^[Yy]') { return }
    New-Item -ItemType Directory -Force -Path $extensionsDir | Out-Null
}

if (Test-Path $target) {
    Write-Host '   Replacing the installed copy...' -ForegroundColor DarkGray
    Remove-Item $target -Recurse -Force
}

if ($mode -eq 'packaged') {
    Copy-Item $packaged $target -Recurse -Force
} else {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    foreach ($item in $bundleContent) {
        $path = Join-Path $clone $item
        if (-not (Test-Path $path)) {
            Write-Host "   Missing from this clone: $item" -ForegroundColor Red
            Remove-Item $target -Recurse -Force
            return
        }
        Copy-Item $path $target -Recurse -Force
    }
}

# Windows marks files that came out of a downloaded zip; pyRevit reads them as
# plain text, but unblocking keeps Defender quiet.
Get-ChildItem $target -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

$buttons = (Get-ChildItem $target -Recurse -Directory |
            Where-Object { $_.Name -like '*.pushbutton' }).Count
Write-Host "   Installed to $target" -ForegroundColor Green
Write-Host "   $buttons tools are ready." -ForegroundColor Green
Write-Host ''
Write-Host '   Start Revit (or click pyRevit > Reload if it is already open).'
Write-Host '   A "Tag Twin" tab appears on the ribbon.'
Write-Host ''
