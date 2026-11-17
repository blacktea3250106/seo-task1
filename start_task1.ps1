# Task1 one-command start for Windows (PowerShell 5+).
#   .\start_task1.ps1            build a clean env, ask for an API key (Enter = replay a recorded run), run
#   .\start_task1.ps1 --offline  skip the key prompt; replay a recorded run, no model calls
#   .\start_task1.ps1 --test     run the Task1 test suite first
# If Windows blocks scripts: powershell -ExecutionPolicy Bypass -File .\start_task1.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv (Python version and package manager, https://docs.astral.sh/uv/) was not found."
    Write-Host "It will be installed with the official script to $env:USERPROFILE\.local\bin without changing your PATH settings."
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $ans = Read-Host "Continue? [Y/n]"
        if ($ans -match '^[Nn]') { Write-Host "Cancelled. Install uv manually and run this script again."; exit 1 }
    }
    $env:UV_NO_MODIFY_PATH = "1"
    powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
uv run --no-project --python 3.12 python start_task1.py @args
exit $LASTEXITCODE
