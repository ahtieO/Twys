# Clean-source package declaration

This source handoff is based on TWYS 2.8, not a newer development branch. The purpose is packaging with Codex; it is **not** a user-facing Windows installer.

**Included:** application source code, HTML/CSS/JS, TWYS logo and `.ico`, packaging scripts, test code (synthetic fixtures only), the current codebase documentation, and instructions for Codex.

**Intentionally excluded:** private Notion exports, user journal rows, imported trade screenshots, SQLite databases, locally cached data, personal settings, access tokens, passwords, generated browser test previews, Python bytecode, pytest caches, build outputs, and old compiled executables.

**Important:** an empty distributable source archive does not remove or reset any user data stored on an existing machine. The installer must respect and preserve existing Windows profile data.

Run the source tests on an isolated temporary data path before publishing the installer. Live API availability remains external to the build process.
