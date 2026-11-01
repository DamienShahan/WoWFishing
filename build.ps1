[CmdletBinding(DefaultParameterSetName = 'Unencrypted')]
param(
    [Parameter(ParameterSetName = 'Password')]
    [Alias('p')]
    [ValidateNotNullOrEmpty()]
    [string]$Password,

    [Parameter(ParameterSetName = 'Prompt')]
    [switch]$PromptForPassword
)

$ErrorActionPreference = 'Stop'
if ($PromptForPassword) {
    $securePassword = Read-Host 'ZIP password' -AsSecureString
    try {
        $Password = [System.Management.Automation.PSCredential]::new('zip', $securePassword).GetNetworkCredential().Password
    } finally {
        $securePassword.Dispose()
    }
    if ([string]::IsNullOrEmpty($Password)) { throw 'ZIP password must not be empty.' }
}
$encryptArchive = $PromptForPassword -or $PSBoundParameters.ContainsKey('Password')

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
if ($encryptArchive) {
    $previousOutputEncoding = $OutputEncoding
    try {
        # Send UTF-8 JSON over stdin so the password is not in Python's command line.
        $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        ConvertTo-Json -InputObject $Password -Compress | & $buildPython "$PSScriptRoot/release_zip.py" `
            "$PSScriptRoot/dist/WoWFishing" "$PSScriptRoot/dist/WoWFishing-Windows.zip"
        if ($LASTEXITCODE -ne 0) { throw 'Encrypted ZIP creation failed.' }
    } finally {
        $OutputEncoding = $previousOutputEncoding
    }
} else {
    Compress-Archive -Path "$PSScriptRoot/dist/WoWFishing" -DestinationPath "$PSScriptRoot/dist/WoWFishing-Windows.zip" -Force
}
Write-Output 'Ready: dist/WoWFishing-Windows.zip'
