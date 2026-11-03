$ErrorActionPreference = 'Stop'
Write-Host ''
Write-Host 'TWYS | TRADE WHAT YOU SEE  -  Windows setup' -ForegroundColor Cyan
$Source = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = Join-Path $env:LOCALAPPDATA 'Programs\TWYS'
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3.10+ was not found. Install Python first, then run INSTALL_WINDOWS.bat again. The standalone EXE build does not require Python.'
}
New-Item -ItemType Directory -Path $Dest -Force | Out-Null
foreach ($file in @('twys_desktop.py','requirements.txt','requirements-desktop.txt','START_WINDOWS.bat','config.example.json')) {
    Copy-Item -LiteralPath (Join-Path $Source $file) -Destination $Dest -Force
}
foreach ($folder in @('twys','static','assets')) {
    $target = Join-Path $Dest $folder
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    Copy-Item -LiteralPath (Join-Path $Source $folder) -Destination $target -Recurse -Force
}
$PythonExe = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv (Join-Path $Dest '.venv')
} else {
    & python -m venv (Join-Path $Dest '.venv')
}
if ($LASTEXITCODE -ne 0) { throw 'Could not set up the isolated Python runtime.' }
$PythonExe = Join-Path $Dest '.venv\Scripts\python.exe'
& $PythonExe -m pip install --disable-pip-version-check -r (Join-Path $Dest 'requirements-desktop.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check internet access and Python version.' }
$Launcher = Join-Path $Dest 'LAUNCH_TWYS.vbs'
$VB = @'
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
app = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = app
cmd = Chr(34) & app & "\.venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & app & "\twys_desktop.py" & Chr(34)
shell.Run cmd, 0, False
'@
[System.IO.File]::WriteAllText($Launcher, $VB, [System.Text.UTF8Encoding]::new($false))
$WScript = Join-Path $env:WINDIR 'System32\wscript.exe'
$Icon = Join-Path $Dest 'assets\twys-icon.ico'
$Programs = Join-Path ([Environment]::GetFolderPath('Programs')) 'TWYS'
New-Item -ItemType Directory -Force -Path $Programs | Out-Null
$Shortcuts = @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'TWYS.lnk'), (Join-Path $Programs 'TWYS.lnk'))
$WShell = New-Object -ComObject WScript.Shell
foreach ($ShortcutPath in $Shortcuts) {
    $Link = $WShell.CreateShortcut($ShortcutPath)
    $Link.TargetPath = $WScript
    $Link.Arguments = '"' + $Launcher + '"'
    $Link.WorkingDirectory = $Dest
    $Link.IconLocation = $Icon
    $Link.Description = 'TWYS | TRADE WHAT YOU SEE by ALL IN INC.'
    $Link.Save()
}
Write-Host 'Installed to:' $Dest -ForegroundColor Green
Write-Host 'A TWYS icon has been added to your Desktop and Start Menu.' -ForegroundColor Green
Write-Host 'Double-click TWYS to open the app with no command prompt window.'
Write-Host 'Your journals and credentials are NOT included in this installer.'
