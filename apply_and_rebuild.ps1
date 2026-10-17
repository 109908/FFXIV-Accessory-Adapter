param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$PatchRoot = $PSScriptRoot

Write-Host 'Step 1/3: Applying the UI/changelog/notice patch...' -ForegroundColor Cyan
py (Join-Path $PatchRoot 'apply_patch.py') $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'Patch application failed. The EXE was not rebuilt.' }

Write-Host 'Step 2/3: Running tests and rebuilding the Windows EXE...' -ForegroundColor Cyan
Push-Location $ProjectRoot
try {
    if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
        py -3.13 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'Could not install/update PyInstaller.' }
    & .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; stopped before packaging.' }
    & .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm FF14-Accessory-Adapter.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    $Exe = Join-Path $ProjectRoot 'dist\FF14-Accessory-Adapter.exe'
    if (-not (Test-Path $Exe)) { throw "Build command finished but EXE was not found: $Exe" }
    Write-Host "Build successful: $Exe" -ForegroundColor Green
    Write-Host 'Open the EXE and verify: startup notice, Changelog button, Notice button, English selector, image-guide buttons, and TTMP2 picker.'
}
finally {
    Pop-Location
}
