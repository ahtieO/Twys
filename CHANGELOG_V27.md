# TWYS 2.7 | Released news results and permanent local deletion

## Why the Actual column was blank

The previous code used `https://nfs.faireconomy.media/ff_calendar_thisweek.json` as its main Forex Factory source. That JSON contains dates, forecasts, previous values and impact levels but **not published Actual figures**, even after an event has finished. The source could never populate the Actual column on its own.

## News corrections

- **Primary source:** ordinary HTTPS read of the public Forex Factory weekly calendar webpage. The app reads the visible `Actual`, `Forecast` and `Previous` table fields rather than treating the JSON feed as complete.
- **All weeks:** requested week pages use `calendar?week=<week>` (tested in the parser with date-appropriate fixture URLs), rather than the nonexistent `ff_calendar_nextweek.json` and `ff_calendar_lastweek.json` exports.
- **Time:** specifically requests a GMT calendar display, verifies the source timezone, normalizes timed events to UTC, then renders them in the Windows computer's timezone. Date-only and tentative events never become fictional timestamps. The bundled build declares `tzdata` for Windows IANA time zone support.
- **Outcomes:** released figures stand out visually. When Actual and Forecast are directly comparable numerically in the same unit, TWYS shows *above / below / at forecast*, never guesses that a high/low print was good or bad for an asset.
- **Updating:** News has a manual **Refresh results** button plus a quiet two-minute refresh of the displayed current week. Successful webpage results are cached by week; cached information is visibly labeled stale if a later connection fails.
- **Outage fallback:** keeps the original weekly export and its clearly stated limitation. Also supports a restricted, no-key, source-attributed US official-agency calendar from XOOMAR. Its scope is not global and it does not supply consensus forecasts. Matching independently supplied actuals to Forex Factory events is exact by date, currency and event name, not fuzzy text similarity.
- **Attribution:** shows the data provider, status, last check time and any separate source of an Actual value. It never fabricates an outcome that a source omitted.

## Recently removed trades

- Added a **Delete forever** button next to **Restore**.
- The user must confirm irreversible deletion.
- Purging deletes the local trade, local private notes, locally stored source-page metadata and any chart images no longer referenced by other trades. It does not modify the original Notion database.
- Only an opaque UID tombstone remains, preventing Notion sync or re-import from recreating the deliberately purged record. There is no undo once deletion completes.
- Existing reversible removal/restore remains unchanged.

## Quality checks

- 54 automated tests pass, including real-looking HTML fixtures covering published Actual values, missing future results, inherited release times, differing impact levels, year rollover, local permanent deletion, and prevention of Notion resynchronization of a purged trade.
- Python source and JavaScript syntax checks pass.
- The browser-based smoke test could not execute: this environment's browser blocks requests to the local test server (`ERR_BLOCKED_BY_ADMINISTRATOR`). No live Forex Factory or XOOMAR requests were possible from this runtime, so live Windows network behavior remains unverified.

## Remaining limitations

- Forex Factory may change its HTML structure, require browser challenges, block automated clients or restrict use. TWYS does not bypass access restrictions. In those cases, the user will see a provider status and limited fallback results; an Actual value cannot be guaranteed for every event.
- The fallback US agency provider covers only selected US releases and usually does not publish forecasts.
- The Windows `.exe` setup is **not compiled in this Linux session**. A Windows CI build configuration is included; this archive is development/update source, not a standalone consumer installer.
- Private user journal data, API tokens, screenshots and locally cached news are **not** included.
