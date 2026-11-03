# TWYS 2.8 — CODEX BUILD REQUEST

**Project:** TWYS | TRADE WHAT YOU SEE, by ALL IN INC.
**Target:** A SINGLE, real, tested Windows installer called `TWYS-Setup.exe`.

This folder contains the complete TWYS 2.8 **application source** with UI assets, back end, tests, and existing Windows installer/build scripts. No user's trading database, Notion exports, cached trade screenshots, secrets, or connection settings are bundled. Test fixtures are synthetic only.

## Your job (Codex)

1. Inspect the source and preserve the TWYS 2.8 user interface and application behavior. No feature redesign.
2. Make the app installable for nontechnical Windows users with **one** `TWYS-Setup.exe`. Double-clicking it should install and register TWYS, create a desktop and Start Menu shortcut, and provide an uninstaller. Users must not have to install Python or run commands.
3. Build the bundled application with PyInstaller (or another demonstrably reliable Windows packaging method) and an NSIS or equivalent setup builder. Bundle all required runtime assets, libraries, and Python components. Use `assets/twys-icon.ico` for installer/shortcuts/taskbar and ensure no Python icon or terminal window appears at launch.
4. Review and fix the existing `BUILD_NATIVE.py`, `installer/windows/twys.nsi`, `.github/workflows/desktop-builds.yml` and `twys_desktop.py` if necessary to make packaging reliable. Keep the local service bound to `127.0.0.1`.
5. Keep code/install files separate from user data. On first install, create an **empty** private journal. On upgrades, **preserve** the user's existing database, Notion connections, settings, and screenshot cache. Uninstall should not silently destroy personal data.
6. Run the existing test suite: `python -m pytest -q` (baseline: 61 tests passed in the provided environment). Fix packaging-related test failures; do not modify financial data or make up sample user trades.
7. Build on a real Windows x64 runner, preferably using the included GitHub Actions workflow. Test the **actual executable and installer**: fresh install, launch, icon, shortcuts, app registration, close, relaunch, uninstall, and no bundled secrets or trading data.
8. Upload the *compiled* `TWYS-Setup.exe` as a downloadable GitHub Actions artifact or GitHub Release asset, together with build/test results. If unable to produce it, report the exact blocker. Do not describe a source ZIP, installer script, or configuration file as the finished installer.

## Security and release requirements

- This archive does not include any personal records. Never request or include the user's Notion token, downloaded private attachments, account data, or journal to build the installer.
- Do not hard-code API keys, passwords, access tokens, or live credentials. Optional market/API integrations should be configured by each user in the installed app.
- Do not expose the development server to the LAN or internet.
- Windows may warn about an **unsigned** installer; code signing is a separate optional step requiring an authorized signing certificate.
- Do not alter or overwrite the user's existing `%APPDATA%\TWYS` data during upgrades.
- Keep provider attributions and required access limits in place.

## Project entry points

- Desktop launcher: `twys_desktop.py`
- Backend/API: `twys/app.py`
- Front end: `static/`
- Existing build script: `BUILD_NATIVE.py`
- NSIS script: `installer/windows/twys.nsi`
- CI: `.github/workflows/desktop-builds.yml`
- Tests: `tests/`
- Requirements: `requirements*.txt`
- App branding: `assets/`

**Completion condition:** provide a genuinely compiled `TWYS-Setup.exe` artifact that passed Windows install and launch checks.
