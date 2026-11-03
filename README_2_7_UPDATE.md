# TWYS 2.7 | News result correction

## What changed

TWYS now attempts to load **Actual, Forecast, and Previous** from the public Forex Factory calendar webpage, instead of relying solely on its scheduled-events JSON export, which does not contain actual results. The Windows computer timezone is applied to the displayed timestamps. Past and upcoming weeks have their own webpage URLs. The News screen shows where results came from, how many events have released actuals and when it last checked. Click **Refresh results** after an important release to force another fetch. While the current week remains on screen, TWYS also checks every two minutes.

Where the Forex Factory webpage cannot be accessed, the application uses limited sources and labels the coverage accordingly. It never creates fictional release results. The XOOMAR fallback reports selected US government economic releases with no consensus forecasts.

## Permanently delete a removed trade

Open **Journal**, click **Recently removed trades**, and select **Delete forever** beside an item. Confirm the action. This permanently deletes the local trade, associated TWYS metadata and private local images that no other trade uses. The Notion original **is not deleted**. A minimal exclusion identifier prevents TWYS from automatically importing that same item again. This cannot be undone. **Restore** still works for entries you have not permanently deleted.

## Update existing source-based Windows installation

1. Exit TWYS completely.
2. Back up `%APPDATA%\\TWYS\\v2\\twys.sqlite3` if it contains data you care about.
3. Extract the TWYS 2.7 source ZIP into its own folder.
4. Run `INSTALL_WINDOWS.bat` from the extracted folder to update the program's source-based installation and dependencies. Your personal data folder is not bundled with the source update.
5. Open TWYS, go to **News**, select the current week and click **Refresh results**. The source status should say *Forex Factory webpage* when the full HTML source is accessible. If it says export-only or limited US fallback, full Actual coverage has not been obtained.

**This is a source update, not the single-file `TWYS-Setup.exe` that has been requested for the finished product.** The Windows compilation job must be run and tested on Windows before that file can be delivered honestly.

For technical detail see `CHANGELOG_V27.md` and `RELEASE_STATUS.md`.
