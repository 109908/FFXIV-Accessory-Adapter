$ErrorActionPreference = 'Stop'
if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    py -3.13 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip pyinstaller
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw '测试失败，停止 EXE 构建。' }
& .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm FF14-Accessory-Adapter.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 构建失败。' }
Write-Host '完成：dist\FF14-Accessory-Adapter.exe'
