$ErrorActionPreference = "Stop"

$pythonExe = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python virtual environment is missing. Create it first with: py -m venv venv"
}

& $pythonExe -m pip install -r (Join-Path $PSScriptRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Installing build requirements failed." }

& $pythonExe -m PyInstaller --noconfirm --clean --onefile --console `
    --name "TurkmenAtBarlayjy" `
    --collect-data sklearn `
    --collect-all uvicorn `
    --collect-all fastapi `
    --collect-all starlette `
    (Join-Path $PSScriptRoot "launcher.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "EXE ready: $(Join-Path $PSScriptRoot 'dist\TurkmenAtBarlayjy.exe')"
