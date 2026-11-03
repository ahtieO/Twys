# Run only on a disposable Windows x64 build runner, never a user's workstation.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $root
$testRoot = Join-Path $env:RUNNER_TEMP 'twys-windows-validation'
if (Test-Path $testRoot) { throw "Validation directory already exists: $testRoot" }
New-Item -ItemType Directory -Path $testRoot | Out-Null
# Exercise the real Windows default data layout in an isolated synthetic profile.
$env:APPDATA = Join-Path $testRoot 'profile'
Remove-Item Env:TWYS_DATA_DIR -ErrorAction SilentlyContinue
$dataDir = Join-Path $env:APPDATA 'TWYS\v2'
$appDir = Join-Path $env:LOCALAPPDATA 'Programs\TWYS'
$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'TWYS.lnk'
$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'TWYS\TWYS.lnk'
$registry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\TWYS'

function Invoke-CheckedProcess([string]$File, [string[]]$Arguments, [int]$Timeout = 150) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit($Timeout * 1000)) {
        $process.Kill()
        throw "Process timed out: $File"
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Process failed ($($process.ExitCode)): $File" }
}
function Invoke-AppCheck([string]$Exe, [string]$Mode, [string]$Name) {
    $report = Join-Path $testRoot ($Name + '.json')
    Invoke-CheckedProcess $Exe @($Mode, '--report', ('"{0}"' -f $report))
    if (!(Test-Path $report)) { throw "App did not write current-run report: $Name" }
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (!$result.ok) { throw "App check failed: $Name" }
    $result | ConvertTo-Json -Depth 10
}

# Verify the PE subsystem and every branded ICO resource byte.
& python installer/windows/verify-pe.py
if ($LASTEXITCODE -ne 0) { throw 'Windowless executable or embedded icon check failed' }
$sourceMark = (Get-FileHash 'static\twys-icon.png' -Algorithm SHA256).Hash
$packedMark = (Get-FileHash 'dist\TWYS\_internal\static\twys-icon.png' -Algorithm SHA256).Hash
if ($sourceMark -ne $packedMark) { throw 'Bundled TWYS mark differs from source' }
$privateFiles = Get-ChildItem 'dist\TWYS' -Recurse -File | Where-Object {
    ($_.Name -match '\.(sqlite3?|db|csv|tsv|xlsx|pfx|p12|pem|key)$' -and
        $_.FullName -ne (Join-Path $root 'dist\TWYS\_internal\certifi\cacert.pem')) -or
    $_.Name -in @('.env', 'config.json', 'secrets.json', 'twys_settings.json')
}
if ($privateFiles) { throw ('Unexpected private-data files in payload: ' + ($privateFiles.Name -join ', ')) }
Invoke-AppCheck (Join-Path $root 'dist\TWYS\TWYS.exe') '--self-test' 'packaged-api'
Invoke-AppCheck (Join-Path $root 'dist\TWYS\TWYS.exe') '--smoke-test' 'packaged-window'

if (Test-Path $appDir) { throw "Unexpected preexisting install: $appDir" }
Invoke-CheckedProcess (Join-Path $root 'TWYS-Setup.exe') @('/S') 300
$installedExe = Join-Path $appDir 'TWYS.exe'
if (!(Test-Path $installedExe) -or !(Test-Path $desktop) -or !(Test-Path $startMenu)) {
    throw 'Installed executable, Desktop or Start Menu shortcut missing'
}
$registration = Get-ItemProperty $registry
if ($registration.DisplayName -ne 'TWYS' -or $registration.InstallLocation -ne $appDir -or
    !$registration.DisplayIcon -or !$registration.UninstallString) { throw 'App registration incomplete' }
$shell = New-Object -ComObject WScript.Shell
foreach ($shortcut in @($desktop, $startMenu)) {
    $link = $shell.CreateShortcut($shortcut)
    if ($link.TargetPath -ne $installedExe -or $link.IconLocation -notlike '*TWYS.exe*') {
        throw "Shortcut target or icon incorrect: $shortcut"
    }
}
Invoke-AppCheck $installedExe '--self-test' 'installed-api'
Invoke-AppCheck $installedExe '--smoke-test' 'installed-window'
Invoke-AppCheck $installedExe '--smoke-test' 'installed-relaunch'
& python -c 'import os,sqlite3; from pathlib import Path; p=Path(os.environ["APPDATA"])/"TWYS"/"v2"/"twys.sqlite3"; c=sqlite3.connect(p); assert c.execute("select count(*) from trades").fetchone()[0]==0, "Fresh install must contain no trades"; c.close()'
if ($LASTEXITCODE -ne 0) { throw 'Empty private journal check failed' }

# Synthetic settings/media sentinels and a database hash must survive upgrade
# and uninstall. No account data, tokens or fabricated user trades are required.
$settings = Join-Path $dataDir 'twys_settings.json'
$media = Join-Path $dataDir 'media\preservation-test.txt'
Set-Content -LiteralPath $settings -Value '{"packaging_test":true}'
Set-Content -LiteralPath $media -Value 'synthetic screenshot-cache preservation sentinel'
$kept = @((Join-Path $dataDir 'twys.sqlite3'), $settings, $media)
$hashes = @{}
foreach ($file in $kept) { $hashes[$file] = (Get-FileHash $file -Algorithm SHA256).Hash }
$unrelated = Join-Path $appDir 'unrelated-user-file.txt'
Set-Content $unrelated 'Preserve files not owned by the installer.'
Invoke-CheckedProcess (Join-Path $root 'TWYS-Setup.exe') @('/S') 300
foreach ($file in $kept) {
    if ((Get-FileHash $file -Algorithm SHA256).Hash -ne $hashes[$file]) { throw "Upgrade changed personal data: $file" }
}
Invoke-AppCheck $installedExe '--smoke-test' 'upgraded-window'
# Launch may legitimately checkpoint SQLite; compare a fresh post-launch hash.
foreach ($file in $kept) { $hashes[$file] = (Get-FileHash $file -Algorithm SHA256).Hash }
Invoke-CheckedProcess (Join-Path $appDir 'uninstall.exe') @('/S', ('_?={0}' -f $appDir))
if ((Test-Path $installedExe) -or (Test-Path $desktop) -or (Test-Path $startMenu) -or (Test-Path $registry)) {
    throw 'Uninstall left app registration, shortcuts or executable behind'
}
if (!(Test-Path $unrelated)) { throw 'Uninstall removed an unrelated file' }
foreach ($file in $kept) {
    if ((Get-FileHash $file -Algorithm SHA256).Hash -ne $hashes[$file]) { throw "Uninstall changed personal data: $file" }
}
Set-Content (Join-Path $testRoot 'windows-install-result.json') '{"ok":true,"fresh_install":true,"gui_launch":true,"relaunch":true,"upgrade":true,"uninstall":true,"data_preserved":true}'
Write-Host 'TWYS Windows executable, fresh install, GUI launch/relaunch, upgrade and uninstall checks passed.'
