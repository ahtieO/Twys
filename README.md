# TWYS 2.8 | Polished trading workstation

The workstation now includes the supplied TWYS mark, refined dark surfaces,
consistent icons, restrained motion, reduced-motion support and keyboard-friendly
search/trade/photo dialogs. Existing trading calculations and integrations remain
unchanged. See [RELEASE_STATUS.md](RELEASE_STATUS.md) for executed checks and
[WINDOWS_RELEASE.md](WINDOWS_RELEASE.md) for the single Windows installer build.

**The source project is not TWYS-Setup.exe.** The improved Windows workflow must
run successfully on a Windows runner to produce and validate that installer.

## Local UI regression checks

Use a disposable data directory when testing. From the repository root:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
TWYS_DATA_DIR=/tmp/twys-ui-data python -m uvicorn twys.app:app --host 127.0.0.1 --port 8765
```

Optional Linux Chromium checks use Playwright and an installed Chromium:

```sh
python -m pip install playwright
TWYS_TEST_URL=http://127.0.0.1:8765 TWYS_TEST_ALLOW_LOCAL_MUTATIONS=1 python tests/browser_smoke.py
```

The opt-in is only for a server using disposable storage: the smoke script toggles
favorites through the real API and restores the original list. Journal/photo
fixtures stay in browser routes. Override `TWYS_TEST_CHROMIUM` if Chromium is not
at `/usr/bin/chromium`. External providers are stubbed; this check is not proof
of live feed availability.

## Earlier 2.8 changes

See [README_2_8_UPDATE.md](README_2_8_UPDATE.md) for upgrade instructions and [RELEASE_STATUS.md](RELEASE_STATUS.md) for test coverage.

# TWYS 2.7 | News Actual results and local permanent deletion

**Latest update:** see [README_2_7_UPDATE.md](README_2_7_UPDATE.md) and [CHANGELOG_V27.md](CHANGELOG_V27.md).

# TWYS 2.6 | Windows development update

**TWYS · TRADE WHAT YOU SEE · BY ALL IN INC.**

This repository contains the TWYS Windows desktop application source. **This ZIP is not the finished Windows installer.** The Windows installer must be built using the Windows build workflow. Do not ask ordinary end users to run the project from Python source.


## November 2, 2026 correction release

1. **Notion edits:** changed pages now refresh by stable page ID, and the Sync Now button performs a full refresh including page-body attachments even if `last_edited_time` did not change. Background polling defaults to 90 seconds on new installations, with a deeper screenshot check every 15 minutes. Older installations may have a saved 300-second interval; change it under Connections. The Journal also checks for successful new sync runs every 30 seconds and reloads when safe. Replaced Notion images receive different cache filenames and the image endpoint disables browser caching. Live Notion credentials were **not** available for end-to-end verification.
2. **Calendar:** Forex Factory's JSON is current-week only, and it has no actual result values. TWYS no longer requests `ff_calendar_lastweek.json` or `ff_calendar_nextweek.json`. Other weeks use the date-range-capable Finance Calendar endpoint, which has partial but independently reported actuals. During the current week TWYS tries to add actuals only where the second provider has an *exact* currency/date/event match. Source and coverage remain identifiable. The Finance Calendar API's free keyless tier has rate limits, and may be inaccessible on a given network.
3. **Macro Desk:** alongside published FRED observations, it now loads a list of economic releases (with actual/forecast/previous when present) and topic-matched official Fed/ECB/BoE headlines. None of this claims a news event caused a price move. External feeds still require live verification on Windows.
4. **Navigation:** Trade Explorer has been removed from the sidebar. Journal remains the sole searchable trade explorer; existing deep links to Trade Explorer redirect to Journal.

### Updating an existing Windows source-based installation

Extract this release into a new directory. Run `INSTALL_WINDOWS.bat` to update the existing source-based installation. This overwrites application code in `%LOCALAPPDATA%\Programs\TWYS` **but does not delete** the SQLite database, media or Notion connection settings under `%APPDATA%\TWYS\v2`. Close TWYS before updating.

For an immediate Notion edit, open Journal and use **Sync latest Notion edits**. For automatic synchronization set the interval to 60–90 seconds under Connections. TWYS needs to be running for polling.

**This is a source update, not a compiled `TWYS-Setup.exe`.** The one-file installer still requires the Windows CI workflow to execute successfully. No external API can be guaranteed to provide every historical release or official actual number; missing values are labeled.

## Changes responding to the October 22 product review

- **Journal:** fixed a route mismatch that caused the Journal's trade table to remain on "Loading..." even after a successful API response. The same table works under `journal22` and `trades`.
- **Market relationships:** AAPL now lists stock/ETF research peers, EURUSD lists related currency benchmarks, and gold lists relevant metals and USD markets. The lists are documented research relationships, **not evidence of price correlations**.
- **Market positioning:** added no-key weekly CFTC financial-futures leveraged-fund position retrieval for supported currency and index futures. This is **delayed futures contracts, not live spot-market buyers and sellers**. Official public source: `https://publicreporting.cftc.gov/resource/gpe5-46if.json`.
- **Public discussions:** attempts instrument-specific Reddit RSS searches and, when no reliable posts are returned, displays direct instrument-specific searches on Reddit, X and Stocktwits. It does not fabricate posts or social sentiment percentages.
- **News:** old saved `calendar_provider=off` configurations now default to the Forex Factory weekly feed. Event results are rendered in TWYS's **own filtered table**. The unfiltered embedded calendar is no longer displayed beneath the USD/High controls. A successfully retrieved weekly export can be used as a labeled local fallback during temporary outages. Forex Factory public exports are subject to provider access and usage restrictions.
- **Navigation:** persistent independent scrollbars for the sidebar, saved watchlist, and research rail; resize handles remain available.
- **Windows branding:** new white, truly transparent SVG/PNG/ICO app mark and explicit Windows application identity to help prevent Python's taskbar icon after packaging.

## What does not work universally

- There is **no reliable universal dataset** that counts every stock, spot FX, crypto or index buyer and seller. CFTC represents delayed US futures, Binance ratios its own exchange accounts, and Myfxbook selected participating accounts with authentication.
- Reddit/X can restrict access to their feeds. Links to public search pages are a fallback, not proof TWYS downloaded those posts.
- Forex Factory's weekly public JSON feed may be rate-limited or inaccessible from a given machine; prior/next week exports are not guaranteed. No events are invented when it fails.
- The running application still depends on TradingView for embedded price charts. Real-time/delayed status depends on the venue and provider.
- Windows EXE and NSIS installer have **not been compiled or visually verified on a Windows machine in this environment**.

## Developer usage

Python 3.12 or newer:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m uvicorn twys.app:app --host 127.0.0.1 --port 8000
```

To open in a native window when the desktop requirements are installed:

```sh
python -m pip install -r requirements-desktop.txt
python twys_desktop.py
```

No journal, screenshot, personal credentials, or user database is preloaded into the source distribution. Each installation stores data in the user profile.

## Produce a single Windows installer

The `.github/workflows/desktop-builds.yml` job on **Windows** builds the packaged desktop executable with PyInstaller, then creates `TWYS-Setup.exe` with NSIS. It runs tests and checks installation, executable self-test, desktop shortcut and uninstall before publishing the installer artifact. This pipeline requires a functioning Windows runner and still needs execution and verification. It may produce an unsigned installer, which can trigger Windows reputation warnings.

The user-facing release should be the single verified `TWYS-Setup.exe`, **not this source ZIP**.
