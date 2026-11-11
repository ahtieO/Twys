# TWYS v1.0 · GitHub launch setup

The code, README and responsive website source are ready on `main`. The Windows CI installer has been built and verified. The remaining steps are **GitHub administrative settings** and require a repository owner to complete in GitHub's own interface.

## 1. Make v1.0 the default code

[Repository settings](https://github.com/ahtieO/Twys/settings) → **General → Default branch → switch to `main`**.

## 2. Make the repository public

Same General settings → **Danger Zone → Change repository visibility → Make public** and confirm.

**Before confirming**: Public access reveals your full commit history. File-path scans found no obvious committed private journal, CSV or credentials, but that is not a full historical secret scan. Review old commits and rotate any credentials that may ever have been committed.

## 3. Publish the Windows release

[Releases](https://github.com/ahtieO/Twys/releases) → edit the draft named **TWYS 1.0 tested Windows installer** → assign public tag **`v1.0.0`** and title **`TWYS 1.0 · Windows Desktop Launch`** → publish with its already-built installer and SHA-256 checksum attached.

Suggested release description:

> TWYS 1.0 is the first public Windows release of Trade What You See by ALL IN INC.
>
> A research-first desktop terminal covering market charts, economic events, macro context, watchlists, Notion-connected private journal review, performance analytics, and an optional AI research assistant.
>
> **Windows x64**. Download `TWYS-Setup.exe` below, verify its checksum, and run setup. No separate Python installation required. The current installer is **unsigned**, so Windows may display an Unknown Publisher warning.
>
> A fresh v1.0 launch starts with an empty local journal. Previous TWYS profiles are not deleted, and may be restored under Data & Backup. TWYS does not place trades or provide investment advice.

**Do not publish a ZIP of the repository as the Windows installer.**

## 4. Activate the product launch website

Once the repository is public: **Settings → Pages → Build and deployment** → **Deploy from a branch** → Branch **`main`**, folder **`/docs`** → **Save**.

The site source is [docs/index.html](docs/index.html). When GitHub Pages reports the site as active, its expected project URL is:

`https://ahtieO.github.io/Twys/`

This URL is **not confirmed active until GitHub Pages says the deployment succeeded**.

## 5. Polish the repository and your profile

- Repository About gear → Description: **TWYS is a Windows market intelligence and trading journal terminal with charts, economic news, macro context, and private Notion analytics.**
- Topics: `trading`, `market-data`, `financial-markets`, `windows-desktop`, `trading-journal`, `economic-calendar`, `market-research`
- Website: enter the Pages URL **after** the deployment works.
- [GitHub Profile Settings](https://github.com/settings/profile) → Bio: **Building TWYS, a desktop market intelligence and trading research terminal. Trade What You See · ALL IN INC.**
- Keep your existing GitHub profile photo unchanged. Pin the TWYS repository on your profile.

## 6. Release hygiene

- The public repo is **source-visible**, not automatically open-source. Decide whether and under what license you want to grant redistribution rights before adding a LICENSE.
- Test the Windows installer on your own computer and check Markets, Watchlist stars, a fresh local profile, the desktop icon, chart imagery and Notion integration.
- Avoid uploading real trading journals, Notion API tokens, user screenshots or personal logs to issues.
- Third-party feeds can be delayed, interrupted or restricted; publish accurate source and data-coverage notices.

The repository cannot be made public, Pages enabled, the draft Release published, or account biography changed through the current GitHub connector actions. Those switches must be performed by the account owner in GitHub.
