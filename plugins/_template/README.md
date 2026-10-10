# Plugin template

Copy this directory to `plugins/<YourPlugin>/`, rename the class, and edit
`manifest.json`. Directories whose name starts with `_` or `.` are ignored by
the loader, so this template is never discovered.

- `manifest.json` — metadata + entry point (validated against the SDK schema).
- `plugin.py` — a `PluginBase` subclass implementing `async def run`.

See `docs/plugin_sdk.md` for the full contract, examples
(`plugins/Wayback`, `plugins/VirusTotal`), and testing guidance.
