# TWYS 2.3 changes from 2.2

- Reworked dark design toward black/white identity, improved readability, subtle animations, white desktop icon, removed in-app logo image.
- Improved local searchable symbol list and added no-key public Binance spot symbol directory for broader crypto discovery.
- Added gold-futures positioning via CFTC official weekly report for XAUUSD/GC source comparison; does not claim live universal buyers/sellers.
- Rebuilt News as a single weekly calendar with Forex Factory's public JSON export parser, local time, filters and consistent weekly pagination. Removed the second competing calendar widget.
- Added extreme-R review threshold so values such as +40,339R no longer distort headline trading analytics without review.
- Added reversible local trash and restore buttons for trades. Upstream Notion deletion/archival detection waits for two successful queries, and automatically restored upstream trades reappear unless explicitly hidden locally.
- Added Notion image caching and gallery viewer, signed image expiry handling, and local media validation.
- Extended Python tests to 27 and added a Windows installation/uninstallation test to GitHub Actions alongside `.exe` self-test.
- Prepared, but **have not yet compiled or installed**, the one-file Windows NSIS setup executable. The source archive is not that installer.
