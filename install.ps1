# Installs the Guided Workflow Assistant skill for Claude Code (Windows).
#
#   irm https://raw.githubusercontent.com/ngumcbrightazongwa-ops/guided-workflow-assistant/main/install.ps1 | iex
#
# Or, from a clone of the repository:   .\install.ps1
# For one project only:                 .\install.ps1 -Project C:\path\to\project
#
# Created by Aneta Prime. MIT licence.

param([string]$Project = '')

$ErrorActionPreference = 'Stop'
$name = 'guided-workflow-assistant'
$zip = "https://github.com/ngumcbrightazongwa-ops/$name/archive/refs/heads/main.zip"

$target = if ($Project) { Join-Path $Project '.claude\skills' } else { Join-Path $HOME '.claude\skills' }
New-Item -ItemType Directory -Force -Path $target | Out-Null

# Use the copy next to this script when run from a clone; otherwise download it.
$local = if ($PSScriptRoot) { Join-Path $PSScriptRoot $name } else { '' }
$temp = $null

if ($local -and (Test-Path (Join-Path $local 'SKILL.md'))) {
    $source = $local
} else {
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("$name-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $temp | Out-Null
    Invoke-WebRequest -Uri $zip -OutFile (Join-Path $temp 'skill.zip') -UseBasicParsing
    Expand-Archive -Path (Join-Path $temp 'skill.zip') -DestinationPath $temp
    $source = Join-Path $temp "$name-main\$name"
}

$dest = Join-Path $target $name
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse -Path $source -Destination $dest

if ($temp) { Remove-Item -Recurse -Force $temp }

Write-Host "Installed $name to $dest"
Write-Host "Restart Claude Code, then ask for a guided workflow assistant or run /$name."
