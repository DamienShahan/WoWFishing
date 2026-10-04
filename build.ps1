$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot '.venv-build/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    & "$PSScriptRoot/.venv/Scripts/python.exe" -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment.' }
}
& $buildPython -m pip install --no-cache-dir -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }
$previousUserBase = $env:PYTHONUSERBASE
$previousBuildCache = $env:PYINSTALLER_CONFIG_DIR
try {
    # Keep build discovery/cache local, including on restricted workstations.
    $env:PYTHONUSERBASE = Join-Path $PSScriptRoot 'build/python-user'
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot 'build/pyinstaller-cache'
    & $buildPython -m PyInstaller --noconfirm WoWFishing.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
} finally {
    $env:PYTHONUSERBASE = $previousUserBase
    $env:PYINSTALLER_CONFIG_DIR = $previousBuildCache
}
Copy-Item -LiteralPath "$PSScriptRoot/QUICKSTART.txt" -Destination "$PSScriptRoot/dist/WoWFishing/QUICKSTART.txt"
Compress-Archive -Path "$PSScriptRoot/dist/WoWFishing" -DestinationPath "$PSScriptRoot/dist/WoWFishing-Windows.zip" -Force
Write-Output 'Ready: dist/WoWFishing-Windows.zip'
