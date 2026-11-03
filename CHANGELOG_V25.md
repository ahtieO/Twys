# TWYS 2.5 fixes

1. Fixed the Journal view's permanent Loading state caused by mismatched route names (`journal22` vs `trades`).
2. Replaced generic unrelated instruments with curated category-specific research peers and explanations.
3. Added support for officially reported CFTC TFF leveraged-money futures positions across selected FX and index markets, with explicit contract/time/direction disclosures.
4. Enhanced public discussion discovery with multiple instrument-alias queries and direct source search links when access fails.
5. Prevented unfiltered third-party calendar widget events from appearing as though they obey TWYS's selected currency and impact filters.
6. Migrated legacy `calendar_provider=off` state to default to the public Forex Factory current-week export; increased caching and preserved last successful current-week response.
7. Fixed independent scrolling in long sidebars/watchlists; retained draggable research cards and adjustable widths.
8. Replaced the desktop icon with a clean white-transparent mark, delivered as SVG, RGBA PNG and a multiresolution Windows ICO. Added Windows AppUserModelID on native launch.
9. Added regression tests and verified Journal and News UI behavior against synthetic test records with Chromium.
10. Updated version display to 2.5. Windows installer remains a build target, not a completed artifact.
