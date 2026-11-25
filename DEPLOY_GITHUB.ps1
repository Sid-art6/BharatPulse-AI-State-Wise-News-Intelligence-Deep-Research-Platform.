# BharatPulse AI v1.6 - publish this source release to the existing GitHub repo.
# Run from the extracted BharatPulse-AI-v1.6 project root.
# This script never copies .env, databases, virtual environments, or cached news.
# No force push. A fresh clone ensures the existing repository cannot be silently modified.
[CmdletBinding()]
param(
    [switch]$StageOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$source = (Get-Location).Path
if (-not (Test-Path (Join-Path $source 'render.yaml')) -or -not (Test-Path (Join-Path $source 'app/main.py'))) {
    throw 'Open PowerShell in the extracted BharatPulse-AI-v1.6 project root before running this script.'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is not installed. Install Git for Windows from https://git-scm.com/download/win and rerun.'
}

$remote = 'https://github.com/Sid-art6/BharatPulse-AI-State-Wise-News-Intelligence-Deep-Research-Platform..git'
$publishDir = Join-Path (Split-Path $source -Parent) 'bharatpulse-github-publish'
if (Test-Path $publishDir) {
    throw "The deployment clone already exists: $publishDir. Rename or remove that COPY (not your source) and rerun."
}

Write-Host 'Cloning your EXISTING GitHub repository...' -ForegroundColor Cyan
& git clone --branch main --single-branch $remote $publishDir
if ($LASTEXITCODE -ne 0) { throw 'GitHub clone failed. Sign in with Git Credential Manager or GitHub CLI, then retry.' }

Push-Location $publishDir
try {
    Write-Host 'Replacing old tracked release files in the temporary clone...' -ForegroundColor Cyan
    & git rm -r --quiet --ignore-unmatch -- .
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage removal of the old release files.' }

    # The release is explicit allowlist; no local developer secrets or state copied.
    foreach ($name in @('app','docs','scripts','tests','.github','.env.example','.gitignore',
                         'README.md','START_HERE.md','render.yaml','requirements.txt',
                         'requirements-dev.txt','DEPLOY_GITHUB.ps1','DEPLOY_RENDER_NOW.md')) {
        $src = Join-Path $source $name
        if (Test-Path $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $publishDir $name) -Recurse -Force
        }
    }
    & git add -A
    if ($LASTEXITCODE -ne 0) { throw 'Git staging failed.' }

    $staged = @(& git diff --cached --name-only)
    if ($staged.Count -eq 0) { Write-Host 'No changes: GitHub already contains this release.'; return }
    $unsafe = @($staged | Where-Object {
        $_ -match '(^|/)(\.env($|\.)|data/|\.venv/|__pycache__/|\.pytest_cache/)' -and $_ -notmatch '(^|/)\.env\.example$' -or $_ -match '\.(db|sqlite|sqlite3|pyc)$'
    })
    if ($unsafe.Count -gt 0) { throw ('REFUSING TO PUSH unsafe files: ' + ($unsafe -join ', ')) }

    Write-Host 'Changed files to publish:' -ForegroundColor Cyan
    $staged | ForEach-Object { Write-Host "  $_" }
    Write-Host 'Release will be published to main without force-pushing.' -ForegroundColor Yellow

    if ($StageOnly) {
        Write-Host "StageOnly: prepared clone at $publishDir; no commit or push performed." -ForegroundColor Yellow
        return
    }

    $confirm = Read-Host 'Type PUBLISH to commit and push this v1.6 source release'
    if ($confirm -cne 'PUBLISH') {
        Write-Host "Cancelled. Your staged preview remains at $publishDir. Nothing was pushed."
        return
    }
    & git commit -m 'Deploy BharatPulse AI v1.6 portfolio preview'
    if ($LASTEXITCODE -ne 0) { throw 'Git commit failed; ensure git config user.name and user.email are set.' }
    & git push origin main
    if ($LASTEXITCODE -ne 0) { throw 'Git push failed. Check GitHub authentication and remote changes; do not force push.' }
    Write-Host 'GitHub updated successfully. Next: create Render Blueprint from the repo (see DEPLOY_RENDER_NOW.md).' -ForegroundColor Green
}
finally { Pop-Location }
