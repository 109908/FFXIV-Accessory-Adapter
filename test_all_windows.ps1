$ErrorActionPreference = 'Stop'
& .\.venv\Scripts\python.exe -m compileall -q .
if ($LASTEXITCODE -ne 0) { throw 'compileall failed' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'unit tests failed' }
