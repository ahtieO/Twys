Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
; makensis changes to the script's directory. All inputs and the single output
; are deliberately rooted at the checkout, regardless of the caller's cwd.
!cd "${__FILEDIR__}/../.."
!define APP_VERSION "2.9.1"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\TWYS"
!define WEBVIEW_KEY "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
Name "TWYS | TRADE WHAT YOU SEE"
Icon "assets\twys-icon.ico"
UninstallIcon "assets\twys-icon.ico"
OutFile "TWYS-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\TWYS"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "TWYS"
VIAddVersionKey /LANG=1033 "CompanyName" "ALL IN INC."
VIAddVersionKey /LANG=1033 "FileDescription" "TWYS Setup"
VIAddVersionKey /LANG=1033 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "ALL IN INC."
!define MUI_FINISHPAGE_RUN "$INSTDIR\TWYS.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open TWYS"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "TWYS requires 64-bit Windows." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  SetRegView 64
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}
FunctionEnd

Function WebViewInstalled
  SetRegView 32
  ReadRegStr $0 HKCU "${WEBVIEW_KEY}" "pv"
  ${If} $0 == ""
    ReadRegStr $0 HKLM "${WEBVIEW_KEY}" "pv"
  ${EndIf}
  ${If} $0 == "0.0.0.0"
    StrCpy $0 ""
  ${EndIf}
  SetRegView 64
FunctionEnd

Section "Install TWYS"
  SetShellVarContext current
  Call WebViewInstalled
  ${If} $0 == ""
    DetailPrint "Installing Microsoft Edge WebView2 Runtime (internet required)..."
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    ; The build workflow downloads and verifies Microsoft's signed bootstrapper.
    File "build\prerequisites\MicrosoftEdgeWebview2Setup.exe"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $1
    Call WebViewInstalled
    ${If} $0 == ""
      MessageBox MB_OK|MB_ICONSTOP "Microsoft Edge WebView2 could not be installed. Connect to the internet and run TWYS Setup again. Your personal data has not been removed." /SD IDOK
      SetErrorLevel 1
      Abort
    ${EndIf}
  ${EndIf}
  SetOutPath "$INSTDIR"
  IfFileExists "$INSTDIR\TWYS.exe" 0 unpack
  ClearErrors
  Delete "$INSTDIR\TWYS.exe"
  ${If} ${Errors}
    MessageBox MB_OK|MB_ICONSTOP "Please close TWYS before installing this update." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  unpack:
  ClearErrors
  File /r "dist\TWYS\*"
  ${If} ${Errors}
    SetErrorLevel 1
    Abort "TWYS files could not be installed. Close TWYS and run Setup again."
  ${EndIf}
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateDirectory "$SMPROGRAMS\TWYS"
  CreateShortCut "$SMPROGRAMS\TWYS\TWYS.lnk" "$INSTDIR\TWYS.exe" "" "$INSTDIR\TWYS.exe" 0
  CreateShortCut "$DESKTOP\TWYS.lnk" "$INSTDIR\TWYS.exe" "" "$INSTDIR\TWYS.exe" 0
  CreateShortCut "$SMPROGRAMS\TWYS\Uninstall TWYS.lnk" "$INSTDIR\uninstall.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "TWYS"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "ALL IN INC."
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\TWYS.exe,0"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetRegView 64
  SetShellVarContext current
  ClearErrors
  Delete "$INSTDIR\TWYS.exe"
  ${If} ${Errors}
    MessageBox MB_OK|MB_ICONSTOP "Please close TWYS before uninstalling." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  Delete "$SMPROGRAMS\TWYS\TWYS.lnk"
  Delete "$DESKTOP\TWYS.lnk"
  Delete "$SMPROGRAMS\TWYS\Uninstall TWYS.lnk"
  RMDir "$SMPROGRAMS\TWYS"
  ; PyInstaller's owned runtime only; never recursively remove a user-selected
  ; install directory that may also contain unrelated files.
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
  ; Personal APPDATA/TWYS journal, settings, credentials and media are retained.
SectionEnd
