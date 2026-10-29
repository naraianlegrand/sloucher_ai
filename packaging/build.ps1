# Build Sloucher: tests, the frozen app (PyInstaller), then the installer (Inno Setup).
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-Python <python.exe>]
# Needs: the model at models\yolov8n-pose_int8.onnx (checked against models\manifest.json),
#        `pip install -e .[dev]` in that Python, and Inno Setup 6.
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

# Conda Pythons keep Tk, ctypes and other DLLs in Library\bin; PyInstaller has to find them
$CondaBin = Join-Path (Split-Path (& $Python -c "import sys; print(sys.executable)") -Parent) "Library\bin"
if (Test-Path $CondaBin) { $env:PATH = "$CondaBin;$env:PATH" }

$manifest = Get-Content models\manifest.json | ConvertFrom-Json
$model = "models\$($manifest.pose.file)"
if (-not (Test-Path $model)) { throw "Missing $model" }
if ((Get-FileHash $model -Algorithm SHA256).Hash.ToLower() -ne $manifest.pose.sha256) { throw "$model doesn't match its checksum" }

Write-Host "1/3 Tests"
& $Python -m pytest -q
if ($LASTEXITCODE) { throw "tests failed" }

Write-Host "2/3 Frozen app"
& $Python -m PyInstaller packaging\sloucher.spec --noconfirm --distpath dist --workpath build --log-level WARN
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Write-Host "3/3 Installer"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }
& $iscc /Q packaging\SloucherSetup.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }

$setup = Get-ChildItem dist\SloucherSetup-*.exe | Sort-Object LastWriteTime | Select-Object -Last 1
"{0}  {1:N1} MB  sha256 {2}" -f $setup.Name, ($setup.Length / 1MB), (Get-FileHash $setup.FullName -Algorithm SHA256).Hash.ToLower()
