# Install Dia for this user on Windows (no administrator rights needed).
#
#   irm https://github.com/Solar9/Dia/releases/latest/download/install.ps1 | iex
#
# $env:DIA_VERSION = "0.1.0"   a release (default: the latest; "main" for development)
$ErrorActionPreference = "Stop"
$Repo = "Solar9/Dia"
$DiaHome = if ($env:DIA_HOME) { $env:DIA_HOME } else { Join-Path $env:LOCALAPPDATA "Dia" }
$Venv = Join-Path $DiaHome "venv"

$Py = $null
foreach ($candidate in @("py -3.13", "py -3.12", "py -3.11", "python")) {
    $parts = $candidate.Split(" ")
    try {
        & $parts[0] $parts[1..9] -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null
        if ($LASTEXITCODE -eq 0) { $Py = $parts; break }
    } catch {}
}
if (-not $Py) { throw "Dia needs Python 3.11 or newer: https://www.python.org/downloads/ (or: winget install Python.Python.3.13)" }

$Version = $env:DIA_VERSION
if (-not $Version) {
    try { $Version = (Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest").tag_name.TrimStart("v") } catch {}
}
if (-not $Version -or $Version -eq "main") {
    $Spec = "dia[ui,app,mobile,chat] @ git+https://github.com/$Repo.git@main"
} else {
    $Spec = "dia[ui,app,mobile,chat] @ https://github.com/$Repo/releases/download/v$Version/dia-$Version-py3-none-any.whl"
}

New-Item -ItemType Directory -Force -Path $DiaHome | Out-Null
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) { & $Py[0] $Py[1..9] -m venv $Venv }
$VPy = Join-Path $Venv "Scripts\python.exe"
& $VPy -m pip install --quiet --upgrade pip
& $VPy -m pip install --quiet --upgrade $Spec
$Dia = Join-Path $Venv "Scripts\dia.exe"
Write-Host "$(& $Dia --version) installed: $Dia"

# `dia` on PATH for this user
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$Scripts = Join-Path $Venv "Scripts"
if ($UserPath -notlike "*$Scripts*") {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$Scripts", "User")
    Write-Host "added $Scripts to your PATH (new terminals see it)"
}
if (-not $env:DIA_NO_SETUP) { & $Dia setup }
