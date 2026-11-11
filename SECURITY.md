# Security and responsible disclosure

TWYS handles locally stored trading journals and optional access credentials. Please **do not post** passwords, Notion integration tokens, API keys, private screenshots, or personal journals in GitHub issues.

If you identify a vulnerability, contact the project maintainer privately through GitHub before disclosing technical details publicly. Do not include live credentials in reports.

## Safety boundaries

- The desktop service is intended to bind only to `127.0.0.1`.
- Runtime Notion data, settings, and private SQLite databases live outside the installed application folder.
- Optional provider credentials are entered by each user, not bundled into source code or installers.
- Public market data is informational and may be delayed or unavailable.
- Releases are currently unsigned. Compare installer checksum and download only from official project releases.

This repository has no bug-bounty program or formal response-time commitment.
