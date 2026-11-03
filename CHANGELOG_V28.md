# TWYS 2.8 patch: photo viewer, research rail, faster Notion edits

- Chart Review thumbnail click now opens fullscreen image lightbox instead of the trade text drawer. Use left/right arrows; a dedicated **View trade details** button opens the source record.
- Trade-detail thumbnails use the same fullscreen viewer. The viewer shows actionable errors when cached Notion image bytes are unavailable.
- Research sidebar cards have matching widths, aligned section headings, and consistent padding, while retaining draggable/reorderable panels.
- **Sync recent edits** no longer forces an expensive full scan of every Notion page and image; it checks revision IDs and refreshes only changed pages. **Recheck all screenshots** is a separate slower deep refresh for unusual cases.
- The background sync no longer starts with a deep page-body scan that can block the first manual sync.
- Reindexing is skipped if an entire Notion source had no changed rows.

Caveats: actual speed depends on Notion API latency, image count, number of changed pages, and connected sources. Live Notion accounts and Windows installation have not been tested in this environment. No existing user database or credentials are bundled.
