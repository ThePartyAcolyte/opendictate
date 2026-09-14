# Auditoría de Deduplicación y UI

## TAREA-36 — Refactorizar `AppProfilesDialog` para usar API de `ConfigManager`

**Hallazgo:** ID-UI-04 | **Severidad:** Media | **Prerrequisito:** Fase 1 completa

### Contexto
El diálogo `AppProfilesDialog` realiza conexiones SQLite manuales en lugar de usar la interfaz abstraída en `ConfigManager`.

### Archivos a modificar
- `opendictate_config_ui.py`

### Cambios requeridos

#### `opendictate_config_ui.py` — Antes (Línea 273-277)
```python
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT app_class FROM app_profiles")
            for row in cursor.fetchall():
```
#### `opendictate_config_ui.py` — Después
```python
        try:
            profiles = self.config_manager.get_all_app_profiles()
            for profile in profiles:
                row = [profile.get("app_class", "")]
```

#### `opendictate_config_ui.py` — Antes (Línea 312-317)
```python
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT system_prompt, enable_vision FROM app_profiles WHERE app_class = ?", (self.current_selected_app,))
            data = cursor.fetchone()
            conn.close()
```
#### `opendictate_config_ui.py` — Después
```python
        try:
            data = self.config_manager.get_app_profile(self.current_selected_app)
```

#### `opendictate_config_ui.py` — Antes (Línea 386-394)
```python
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO app_profiles (app_class, system_prompt, enable_vision) VALUES (?, '', 0)",
                    (app_name,)
                )
                conn.commit()
                conn.close()
```
#### `opendictate_config_ui.py` — Después
```python
            try:
                self.config_manager.save_app_profile(app_name, "", False)
```

#### `opendictate_config_ui.py` — Antes (Línea 409-417)
```python
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE app_profiles SET system_prompt = ?, enable_vision = ? WHERE app_class = ?",
                (prompt, vision, self.current_selected_app)
            )
            conn.commit()
            conn.close()
```
#### `opendictate_config_ui.py` — Después
```python
        try:
            self.config_manager.save_app_profile(self.current_selected_app, prompt, bool(vision))
```

#### `opendictate_config_ui.py` — Antes (Línea 430-435)
```python
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM app_profiles WHERE app_class = ?", (self.current_selected_app,))
            conn.commit()
            conn.close()
```
#### `opendictate_config_ui.py` — Después
```python
        try:
            self.config_manager.delete_app_profile(self.current_selected_app)
```

### Verificación
```bash
grep -n 'sqlite3.connect' opendictate_config_ui.py
```

## TAREA-37 — Reemplazar `get_open_apps()` por `get_open_windows_list()`

**Hallazgo:** ID-UI-05 | **Severidad:** Baja | **Prerrequisito:** Fase 1 completa

### Contexto
Existe una duplicación funcional en la recolección de ventanas activas entre `opendictate_config_ui.py` y `core/window_utils.py`.

### Archivos a modificar
- `opendictate_config_ui.py`

### Cambios requeridos

#### `opendictate_config_ui.py` — Antes (Eliminar L326-351)
```python
    def get_open_apps(self) -> List[str]:
        # ... bloque original ...
        return sorted(list(apps))
```
#### `opendictate_config_ui.py` — Después
*(Eliminar el método `get_open_apps`)*

#### `opendictate_config_ui.py` — Antes (Línea 369-370)
```python
        for app in self.get_open_apps():
            combo.append_text(app)
```
#### `opendictate_config_ui.py` — Después
```python
        from core.window_utils import get_open_windows_list
        for w in get_open_windows_list():
            combo.append_text(f"{w.get('title', '')} [{w.get('class', '')}]")
```

### Verificación
```bash
grep -n 'def get_open_apps' opendictate_config_ui.py
```

## TAREA-38 — Centralizar `get_omarchy_palette()` en `core/hardware.py`

**Hallazgo:** ID-UI-07 | **Severidad:** Baja | **Prerrequisito:** Fase 1 completa

### Contexto
La función `get_omarchy_palette()` está duplicada de forma idéntica en `ui/settings_tui.py` y `ui/wizard_tui.py`.

### Archivos a modificar
- `core/hardware.py`
- `ui/settings_tui.py`
- `ui/wizard_tui.py`

### Cambios requeridos

#### `core/hardware.py` — Después
Insertar la función completa al archivo.

#### `ui/settings_tui.py` — Antes (Líneas 97-149)
```python
def get_omarchy_palette() -> Dict[str, str]:
    # ... cuerpo de la funcion ...
    return palette
```
#### `ui/settings_tui.py` — Después
```python
from core.hardware import get_omarchy_palette
```

#### `ui/wizard_tui.py` — Antes (Líneas 64-116)
```python
def get_omarchy_palette() -> Dict[str, str]:
    # ... cuerpo de la funcion ...
    return palette
```
#### `ui/wizard_tui.py` — Después
```python
from core.hardware import get_omarchy_palette
```

### Verificación
```bash
python3 -c "from core.hardware import get_omarchy_palette; print('OK')"
```

## TAREA-39 — Centralizar generación de autostart `.desktop` en `ConfigManager`

**Hallazgo:** ID-INFRA-06 | **Severidad:** Media | **Prerrequisito:** Fase 1 completa

### Contexto
Tanto el cliente como el config_ui generan de forma independiente (y con variaciones) el archivo `.desktop` de autostart. Debe abstraerse a `ConfigManager`.

### Archivos a modificar
- `core/config.py`
- `opendictate-client.py`
- `opendictate_config_ui.py`

### Cambios requeridos

#### `core/config.py` — Después
Insertar el método en `ConfigManager`:
```python
    def set_autostart_enabled(self, enabled: bool) -> None:
        """Enable or disable system autostart for OpenDictate daemon."""
        import os
        autostart_dir = os.path.expanduser("~/.config/autostart")
        autostart_path = os.path.join(autostart_dir, "opendictate.desktop")
        
        if enabled:
            os.makedirs(autostart_dir, exist_ok=True)
            install_dir = os.path.expanduser("~/.local/share/opendictate")
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=OpenDictate
Comment=Background daemon for global voice dictation using faster-whisper
Exec={install_dir}/.venv/bin/python {install_dir}/opendictate-daemon.py --force-start
Icon={install_dir}/img/logo.png
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
            with open(autostart_path, "w") as f:
                f.write(desktop_content)
        else:
            if os.path.exists(autostart_path):
                os.remove(autostart_path)
```

#### `opendictate-client.py` — Antes
*(Lógica manual en L131-145)*
#### `opendictate-client.py` — Después
```python
        config_manager.set_autostart_enabled(True) # o False según lógica
```

#### `opendictate_config_ui.py` — Antes
*(Lógica manual en L1942-1955)*
#### `opendictate_config_ui.py` — Después
```python
        self.config_manager.set_autostart_enabled(self.autostart_switch.get_active())
```

### Verificación
```bash
python3 -c "from core.config import ConfigManager; print(hasattr(ConfigManager, 'set_autostart_enabled'))"
```
