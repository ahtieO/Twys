$ErrorActionPreference='Stop'
$Dest=Join-Path $env:LOCALAPPDATA 'Programs\TWYS'
$Desktop=Join-Path ([Environment]::GetFolderPath('Desktop')) 'TWYS.lnk'
$StartMenu=Join-Path ([Environment]::GetFolderPath('Programs')) 'TWYS'
if(Test-Path $Desktop){Remove-Item $Desktop -Force}
if(Test-Path $StartMenu){Remove-Item $StartMenu -Recurse -Force}
if(Test-Path $Dest){Remove-Item $Dest -Recurse -Force}
Write-Host 'TWYS application removed. Personal data under %APPDATA%\TWYS\v2 was preserved.'
