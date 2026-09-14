# Auditoría de Logging y Manejo de Errores

## TAREA-40 — Reemplazar `print()` por `logging` en `config_ui.py` y `launch_wizard.py`

**Hallazgo:** ID-UI-06 | **Severidad:** Media | **Prerrequisito:** Fase 4 completa

### Contexto
Se identificaron múltiples llamadas a `print()` en lugar de utilizar el sistema unificado de `logging`, lo cual provoca que estos mensajes no queden registrados en `daemon.log`.

### Archivos a modificar / crear
- `opendictate_config_ui.py`
- `launch_wizard.py`

### Cambio requerido

#### `opendictate_config_ui.py` — Antes (línea 288)
```python
            self.listbox.show_all()
        except Exception as e:
            print("Error loading profiles:", e)
```
#### `opendictate_config_ui.py` — Después
```python
            self.listbox.show_all()
        except Exception as e:
            logging.error(f"Error loading profiles: {e}")
```

#### `opendictate_config_ui.py` — Antes (línea 323)
```python
            if data:
                self.prompt_view.get_buffer().set_text(data[0] if data[0] else "")
                self.vision_switch.set_active(bool(data[1]))
        except Exception as e:
            print("Error loading profile details:", e)
        self._updating_ui = False
```
#### `opendictate_config_ui.py` — Después
```python
            if data:
                self.prompt_view.get_buffer().set_text(data[0] if data[0] else "")
                self.vision_switch.set_active(bool(data[1]))
        except Exception as e:
            logging.error(f"Error loading profile details: {e}")
        self._updating_ui = False
```

#### `opendictate_config_ui.py` — Antes (línea 419)
```python
            conn.commit()
            conn.close()
        except Exception as e:
            print("Auto-save profile error:", e)
```
#### `opendictate_config_ui.py` — Después
```python
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Auto-save profile error: {e}")
```

#### `launch_wizard.py` — Antes (línea 27)
```python
            wizard = FirstRunWizard(
                config_mgr,
                on_finish=lambda cfg: print("Wizard finished with config:", cfg)
            )
```
#### `launch_wizard.py` — Después
```python
            import logging
            wizard = FirstRunWizard(
                config_mgr,
                on_finish=lambda cfg: logging.info(f"Wizard finished with config: {cfg}")
            )
```

#### `launch_wizard.py` — Antes (línea 33)
```python
            Gtk.main()
            return
        except Exception as e:
            print(f"Error opening GTK wizard: {e}. Falling back to TUI...")
```
#### `launch_wizard.py` — Después
```python
            Gtk.main()
            return
        except Exception as e:
            import logging
            logging.warning(f"Error opening GTK wizard: {e}. Falling back to TUI...")
```

### Verificación
```bash
grep -n '^\s*print(' opendictate_config_ui.py launch_wizard.py
```

---

## TAREA-41 — Agregar `logging.debug()` en bloques `except` silenciosos de `core/hardware.py` e `core/ipc.py`

**Hallazgo:** ID-DAEMON-09 | **Severidad:** Baja | **Prerrequisito:** Fase 4 completa

### Contexto
Varios bloques `try-except` ocultan silenciosamente las excepciones usando `pass`, lo que dificulta el rastreo de fallos en la detección de hardware o manejo de IPC.

### Archivos a modificar / crear
- `core/hardware.py`
- `core/ipc.py`

### Cambio requerido

#### `core/hardware.py` — Antes (importación)
```python
import os
import shutil
import subprocess
```
#### `core/hardware.py` — Después
```python
import os
import shutil
import subprocess
import logging
```

#### `core/hardware.py` — Antes (línea 28, 109, 125, 139, 165)
```python
    except Exception:
        pass
```
#### `core/hardware.py` — Después
```python
    except Exception as e:
        logging.debug(f"Hardware detection error: {e}")
```
*(Aplicar patrón similar inyectando el contexto relevante en L28, L109, L125, L139, L165)*

#### `core/ipc.py` — Antes (línea 79, 84)
```python
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except Exception:
                pass
```
#### `core/ipc.py` — Después
```python
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logging.debug(f"Error closing socket: {e}")
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except Exception as e:
                logging.debug(f"Error removing socket file: {e}")
```

### Verificación
```bash
python3 -c "from core.hardware import get_gpu_info; print('OK')"
```

---

## TAREA-42 — Agregar `logging.debug()` en bloques `except` silenciosos del daemon

**Hallazgo:** ID-DAEMON-25 | **Severidad:** Baja | **Prerrequisito:** Fase 4 completa

### Contexto
El daemon maestro tiene bloques `except` silenciosos en operaciones críticas como exportación de estado o chequeos de D-Bus.

### Archivos a modificar / crear
- `opendictate-daemon.py`

### Cambio requerido

#### `opendictate-daemon.py` — Antes (línea 316, 625, 699, 1869)
```python
            except Exception:
                pass
```
#### `opendictate-daemon.py` — Después
```python
            except Exception as e:
                logging.debug(f"Ignored exception: {e}")
```

### Verificación
```bash
grep -n 'except Exception:\s*$\|except:\s*$' opendictate-daemon.py | wc -l
```

---

## TAREA-43 — Agregar logging en `except` silenciosos de UI (`wizard.py`, `tray.py`, `settings_tui.py`)

**Hallazgo:** ID-UI-16 | **Severidad:** Baja | **Prerrequisito:** Fase 4 completa

### Contexto
La interfaz gráfica (UI) oculta excepciones de inicialización o llamadas GTK fallidas mediante bloques `except` vacíos.

### Archivos a modificar / crear
- `ui/wizard.py`
- `ui/tray.py`
- `ui/settings_tui.py`

### Cambio requerido

#### `ui/tray.py` — Antes (varias líneas)
```python
            except Exception: pass
```
#### `ui/tray.py` — Después
```python
            except Exception as e:
                logging.debug(f"Tray GTK error ignored: {e}")
```

#### `ui/wizard.py` — Antes (varias líneas)
```python
            except Exception:
                pass
```
#### `ui/wizard.py` — Después
```python
            except Exception as e:
                logging.debug(f"Wizard GTK error ignored: {e}")
```

#### `ui/settings_tui.py` — Antes (varias líneas)
```python
    except Exception:
        pass
```
#### `ui/settings_tui.py` — Después
```python
    except Exception as e:
        import logging
        logging.debug(f"TUI error ignored: {e}")
```

### Verificación
```bash
grep -n 'except Exception:\s*$\|except:\s*$' ui/tray.py ui/wizard.py ui/settings_tui.py | wc -l
```
