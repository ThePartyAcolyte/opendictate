# Technical Debt & Known Limitations

This document tracks technical debt, pending architectural refactors, and known environment-specific limitations across the OpenDictate codebase.

---

## Active Technical Debt

### `TD-001`: Dynamic Language Hot-Reload in GNOME Shell Context Menu

- **Component**: GNOME Shell Extension (`gnome-extension/com.kirulab.opendictate@kirulab.com/extension.js`)
- **Severity**: Low (Visual / Localization UX)
- **Status**: Open

#### Description
While the Settings window (`opendictate_config_ui.py`) and background daemon (`opendictate-daemon.py`) successfully reload and persist UI language changes in real time (updating SQLite and `/tmp/opendictate_state.json`), the context menu labels of the GNOME Shell extension (`PanelMenu.Button` -> `PopupMenu.PopupMenuItem` / `PopupMenu.PopupSwitchMenuItem`) retain their initial instantiated strings and do not dynamically re-render in GNOME Shell 50+ without restarting the GNOME Shell session.

#### Technical Analysis & Root Cause
1. **Clutter/St Actor Hierarchy Retention**: In GNOME Shell 45–50 (ESM), mutating properties (`.text` / `.set_text()`) on child `St.Label` actors within an already-constructed `PopupMenu` does not reliably force Clutter layout invalidation and redraw of parent menu rows.
2. **Module Lifecycle in SpiderMonkey**: Once an ES module extension is loaded by GNOME Shell, the JS module remains resident in memory. Disabling/enabling the extension via DBus calls the lifecycle hooks (`disable()`/`enable()`) but does not reload script modules from disk.

#### Proposed Future Resolution
1. **Dynamic Menu Rebuilding**: Refactor the extension context menu from in-place property mutation to a full tear-down/rebuild pattern (`this.menu.removeAll()` followed by a clean `this._buildMenu(currentLang)`) whenever `open-state-changed` is emitted or when `ui_language` changes in `/tmp/opendictate_state.json`.
2. **Native GNOME Gettext Integration**: Migrate extension-side strings to the standard GNOME Shell `gettext` domain via `Extension.initTranslations()` and compiled `.mo` translation catalogs.
