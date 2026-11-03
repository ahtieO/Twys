# Build the TWYS Windows installer

The intended end-user download is **TWYS-Setup.exe**. It installs TWYS, its Python
runtime, libraries, static assets and supplied logo. Users do not install Python
or run commands. A source ZIP is developer material, not the installer.

## Windows build and validation

Put this project in the `ahtieO/Twys` repository, including `.github/workflows`.
In GitHub Actions, run **TWYS Windows setup** with **Run workflow** on the branch
containing these changes. The job uses a Windows x64 runner and Python 3.12.
It can also run when a version tag beginning with `v` is pushed.

The workflow:

1. Installs build dependencies and runs the Python regression suite.
2. Uses PyInstaller to build the windowless `dist/TWYS/TWYS.exe` application.
3. Downloads Microsoft's WebView2 bootstrapper and verifies its Authenticode
   signature before bundling it. WebView2 is installed only when missing;
   installing that prerequisite requires internet access.
4. Uses NSIS to produce the single `TWYS-Setup.exe` distribution file.
5. Checks the x64 GUI subsystem and exact supplied icon resources; starts both
   the packaged and installed executable with the actual Edge WebView2 window.
6. Verifies Desktop/Start Menu shortcuts, app registration, an empty journal,
   close/relaunch, an upgrade, and uninstall. Synthetic profile sentinels verify
   that database/settings/media survive upgrade and uninstall. The service stays
   bound to `127.0.0.1` on a reserved port.
7. Uploads **TWYS-Setup-unsigned** only after those checks pass. Download the
   artifact and extract `TWYS-Setup.exe`. A SHA-256 checksum accompanies it.
   **TWYS-Windows-test-results** contains the build/test evidence, including on
   failed builds when results are available.

Run `installer/windows/verify-install.ps1` only on a disposable Windows runner;
it installs and uninstalls TWYS in that runner's user profile. It is not an
end-user troubleshooting script.

## Data and branding

- The application and shortcuts are called **TWYS** and use `assets/twys-icon.ico`.
- Private data lives separately at `%APPDATA%\TWYS\v2`. No journal, credentials,
  or private screenshots are included in the build inputs.
- Uninstall retains the private profile. Keep a backup before updating important
  journals; inspect the Windows results before distributing a build.
- The installer is unsigned unless a separate authorized signing step is added.
  Windows may show a reputation warning. No signing certificate is bundled.

## Current verification boundary

This revision was developed and tested on Linux. See `RELEASE_STATUS.md` for the
checks actually executed. The Windows workflow must finish successfully before
calling its executable a tested release. A Linux syntax check of NSIS is not a
Windows installation or desktop test.
