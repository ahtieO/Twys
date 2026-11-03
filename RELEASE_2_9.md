# TWYS 2.9 · Windows Update

Scope: Only the three user-requested changes.

1. **Classic branding:** Text-only TWYS in the application. The Windows executable, installer, taskbar and desktop shortcut use the earlier white TWYS wordmark and market arrow, restored from the original tracked `static/twys-mark.png`. The Windows build creates the transparent multi-size ICO before tests and packaging.
2. **Appearance:** Light and Dark switch at the top of the terminal. Dark remains the default. The setting is local to this desktop application and is remembered between launches. Embedded TradingView charts are rebuilt with the selected color theme when the active page reloads.
3. **Personal-data profiles:** When TWYS first starts and finds an existing legacy journal, a native Windows prompt offers Continue Existing, Start Fresh or Cancel. Fresh starts live in `%APPDATA%\\TWYS\\profiles\\fresh-...`, leaving the legacy `%APPDATA%\\TWYS\\v2` journal untouched. From **Data & backup**, use the new LOCAL DATA PROFILE panel to choose Existing or Start Fresh for the next launch. **Close and reopen** TWYS to apply a new profile selection. Newly created profiles have separate Notion API credentials in Windows Credential Manager.

The default installer does not package user journals or saved tokens. Normal upgrades never delete the legacy journal. All other analytics, market data and journal features remain unchanged.

## Windows setup

The `TWYS Windows setup` GitHub Actions workflow builds and tests the single-file unsigned `TWYS-Setup.exe` installer on Windows. The workflow restores the icon, runs the full test suite, builds the app, validates installation/launch/upgrade/uninstall, and uploads an Actions artifact named `TWYS-Setup-unsigned`.

Do not download a repository source ZIP and mistake it for the executable.

## Known limitations

The optional Light mode uses an override stylesheet over earlier dark-theme CSS. Embedded third-party widgets control some of their own styles. User settings are stored in the browser webview local storage; the selected data profile is stored in `%APPDATA%\\TWYS\\profile_selection.json`. The profile switch does not purge prior data or credentials.

This release does not alter external feeds or Notion sync behavior.