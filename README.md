# TWYS | Trade What You See

**Market intelligence meets personal trading research.**  
Windows desktop terminal · **v1.0** · By **ALL IN INC.**

> Trade what you see. Understand what you trade.

TWYS is a research-first Windows desktop application built to make financial-market data easier to navigate, compare, and understand. It combines public market context with your own private trading journal. **TWYS is not a broker**. It does not execute trades, hold funds, or provide personalized investment advice.

## Product launch page

The responsive, black-and-white TWYS product landing page is maintained in **[docs/index.html](docs/index.html)**. It introduces the terminal, explains the core workspaces, links to official releases and describes the privacy-first, research-only scope.

To publish it as a website, set the repository to **Public**, then open **Settings → Pages → Build and deployment**, choose **Deploy from a branch**, select **main** and **/docs**, and save. GitHub will display the live Pages URL once deployment succeeds.

## Explore TWYS

| Workspace | Purpose |
| --- | --- |
| **Markets** | Search financial instruments, browse TradingView-powered charts, and find available market context |
| **Watchlist** | Save your markets and view charts, sourced positioning, and public discussion in one place |
| **News** | Follow the economic calendar, reported results when available, and official financial headlines |
| **Macro Desk** | Understand interest rates, Treasury yields, inflation, and cross-market context using sourced observations |
| **Journal** | Connect your Notion trading journal, view notes and screenshots, and sync recorded changes |
| **Performance & Psychology** | Review results in R, setup quality, recurring behaviors, and recorded emotions |
| **Research assistant** | Optional connection to local Ollama or user-supplied AI APIs; the terminal works without AI |

**Source-first data:** TWYS labels missing, delayed, and source-specific data. There is no universal feed showing every buyer and seller across all financial markets. Positions reported by regulators or individual platforms are limited to the participants they cover.

## Download for Windows

1. Open [Releases](https://github.com/ahtieO/Twys/releases).
2. Choose the latest **tested v1.0 Windows release** and download **`TWYS-Setup.exe`**.
3. Run Setup. No separate Python installation is required.
4. Launch TWYS using the desktop or Start Menu shortcut.

**Windows x64 only for now.** The installer is unsigned, so Windows may show an Unknown Publisher warning. Verify the file was obtained from this repository and check the published checksum. If no verified public Release is available, do not confuse the source ZIP with the compiled installer.

### Your data stays separate

- **A clean v1.0 launch starts with an empty local profile**. It does not import previous TWYS trades automatically.
- Existing TWYS profiles are preserved and can be restored through **Data & Backup → Local Data Profile**, followed by a restart.
- Personal SQLite databases, screenshots, Notion tokens, and saved settings are **never part of the installer**.
- TWYS starts a local service bound to `127.0.0.1`, not an internet-facing trading server.

## How it's built

Python and FastAPI backend, a desktop window powered by WebView2, and a JavaScript UI. Market charts and selected data feeds are supplied by attributed third-party services. Packaging uses PyInstaller and NSIS; GitHub Actions runs automated checks and Windows installation tests.

Developers can run tests with Python 3.12:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

See [WINDOWS_RELEASE.md](WINDOWS_RELEASE.md) for packaging, [SECURITY.md](SECURITY.md) for responsible reporting, and [CHANGELOG.md](CHANGELOG.md) for public release notes.

## Status and limitations

TWYS 1.0 is the **first public release line**, following private 2.x development iterations. External news, social feeds, price data, and Notion integrations depend on source availability, network connectivity, and individual provider rights. Some feeds are delayed or incomplete. The presence of a market chart does not imply real-time execution-grade prices.

**Built by ALL IN INC.**  
**TWYS — Trade What You See.**

*Not affiliated with TradingView, Notion, Forex Factory, Reddit, or the other referenced providers. All respective trademarks belong to their owners. This repository being publicly readable does not automatically grant a software redistribution license.*
