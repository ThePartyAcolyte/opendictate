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

---

### `TD-002`: Conectar `parse_verbal_punctuation` al pipeline de transcripción

- **Componente**: Engine (`core/engine.py:220-251`)
- **Severidad**: Baja (Funcionalidad pendiente)
- **Estado**: Open

#### Descripción
La función `parse_verbal_punctuation` reemplaza la puntuación hablada (e.g., "punto", "coma", "nuevo párrafo") por sus símbolos correspondientes. Está completamente implementada y probada individualmente, pero no está conectada activamente al flujo principal de salida de transcripción del motor.

#### Trabajo Pendiente
1. Catálogo multilingüe de frases por idioma (`i18n`).
2. Configuración en la interfaz gráfica para activar/desactivar la sustitución verbal de puntuación.
3. Integración en el pipeline final de entrega de texto del daemon.

---

### `TD-003`: Finalización del Roadmap e Integración UI para Comandos de Voz y Calibración AEC

- **Componente**: Voice Commands (`core/voice_commands.py`, `core/aec.py`, `opendictate-daemon.py`)
- **Severidad**: Media (Feature Work In Progress)
- **Estado**: Open (Roadmap)

#### Descripción
El subsistema de comandos de voz interactivos y la calibración AEC (Eco Acústico / Piso de Ruido) se encuentra desarrollado a nivel de lógica de motor en `core/voice_commands.py` y `opendictate-daemon.py`. La interfaz gráfica en el asistente inicial (`ui/wizard.py`) fue retirada para simplificar la bienvenida, pero la funcionalidad core permanece conservada en el proyecto para su lanzamiento completo.

#### Trabajo Pendiente
1. Diseñar un panel dedicado en la interfaz de Ajustes (`opendictate_config_ui.py`) para enrolar muestras de voz y ajustar sensibilidad.
2. Finalizar integración de comandos predefinidos ("Empezar", "Enviar", "Pausar", "Cancelar").
