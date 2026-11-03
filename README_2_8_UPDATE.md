# TWYS 2.8 | Chart Review and sync performance update

## What changed

1. **Chart Review now opens photographs, not a source-record drawer.** Click anywhere on a chart thumbnail to open the fullscreen photo viewer. Navigate with the left/right arrows or keyboard arrow keys. Click the photo to zoom, press Escape to close. The **View trade details** button opens the source record separately. Screenshots inside the trade record also open the fullscreen viewer.
2. **Market rail cards are aligned.** Their widths, title alignment, spacing and minimum sizes are consistent; reordering and rail resizing remain supported.
3. **Notion quick sync is faster by design.** The Journal button **Sync recent edits** checks page revision metadata and only revisits changed pages. **Recheck all screenshots** is available for a slower complete body-image refresh, especially when a Notion attachment was replaced without an observable page revision. Unchanged cached files are reused even if a note in the same record changes. A full background body scan is no longer triggered immediately on app startup. These improvements reduce unnecessary work but cannot guarantee a fixed completion time because Notion API latency and rate limiting vary.

## Update an existing Windows source installation

- Completely exit TWYS.
- Back up your data file under `%APPDATA%\TWYS\v2\twys.sqlite3` before upgrading.
- Extract this source update to a new directory.
- Run `INSTALL_WINDOWS.bat` to update the already-installed source-based TWYS app.
- Open **Chart review**, click a thumbnail. Use **View trade details** if you want its notes.
- Open **Journal** and choose **Sync recent edits**. Use **Recheck all screenshots** only when a changed screenshot is still stale.

The personal SQLite journal, Notion integration token/settings, and cached media are stored in the Windows user profile and **are not shipped in this ZIP**. The update script is designed to preserve them; still make a backup.

## Verification and limitations

- 61 local automated tests passed, including API image bytes, revision-based fast-sync behavior, and reuse of unchanged cached images.
- An isolated browser interaction test verified that clicking a chart-review thumbnail opens the fullscreen layer and the separate detail button opens the trade record, with no JavaScript errors. It used synthetic data rather than an authenticated Notion account.
- No live Notion synchronization was tested with your credentials; the time saved on your PC is not measured.
- This is still **source-based Windows update material**, not the single compiled `TWYS-Setup.exe`. Native compilation/install testing requires a Windows build runner. The existing Windows installer workflow remains in `.github/workflows/desktop-builds.yml`.
