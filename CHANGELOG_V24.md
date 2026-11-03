# TWYS 2.4 | Workstation correction pass

This is a **development source release**, NOT a verified one-click Windows installer.

Implemented in this pass:
- Removed the extra inert 1W/1M/3M/1Y/5Y text above the TradingView chart. Its own controls remain.
- Removed the three mini charts that repeatedly displayed the wrong time window rather than presenting misleading performance.
- Added an actual watchlist research workspace: select saved markets and inspect a chart, linked positioning records, social discussions, and relevant scheduled news.
- Removed the duplicate `Overview` and `Removed trades` navigation entries. Journal opens the trade explorer, while journal-local recovery remains available.
- Added `Macro Desk` using public FRED downloadable observations for effective fed funds rates, Treasury yields, real yields, breakeven inflation, broad dollar index, EURUSD reference, and US CPI. Dates and data frequency are displayed. It does not infer causality from correlation.
- Added sidebar width drag resize, research rail drag resize, and drag-to-reorder for the right research panels; positions persist in localStorage.
- Added a fallback TradingView economic calendar within the primary News area only when the currently selected week cannot be fetched; next/previous-week provider limitations remain explicit.
- Replaced packaged desktop `.png` and `.ico` assets with a centered version of the approved transparent white TWYS mark. In-app branding stays text-only.

Tests: 31 unit/integration checks passed with `PYTHONPATH=. pytest -q`. JavaScript parsed successfully under Node.

**Outstanding:** Forex Factory and other internet providers are not verified on the user's Windows environment, generic forex/stocks positioning still requires suitable permitted providers, the complete drag-and-drop UX is not graphically verified, no precompiled `TWYS-Setup.exe` was produced. Native Windows compilation must occur on Windows or a Windows CI runner. Do not distribute source ZIP as though it is a one-click installer.
