# DevLog: Fase 3 — Empaquetado e Instalación

**Fecha:** 2026-09-14
**Estado:** Completado
**Fase de Auditoría:** Fase 3 (TAREA-12 a TAREA-20)

## Resumen de Cambios

Esta fase corrigió y homogenizó todos los scripts de instalación local, paquetes distribuidos (Debian `.deb` y Arch Linux `.pkg.tar.zst`), desinstalación y el entorno de plugins de la aplicación.

### Tareas Ejecutadas

1. **TAREA-12: Definición de `$OPENDECK_PLUGINS_DIR`**
   - **Archivo:** `install.sh`
   - **Descripción:** Se definió la variable `OPENDECK_PLUGINS_DIR="$HOME/.config/opendeck/plugins"` permitiendo la instalación automática del plugin de Stream Deck / OpenDeck.

2. **TAREA-13: Permisos de Ejecución a `opendictate_config_ui.py`**
   - **Archivo:** `install.sh`
   - **Descripción:** Se agregó `chmod +x "$INSTALL_DIR/opendictate_config_ui.py"` en el instalador.

3. **TAREA-14: Instalación vía `requirements.txt`**
   - **Archivo:** `install.sh`
   - **Descripción:** Se sustituyó la lista manual de paquetes Python por `uv pip install -r requirements.txt --python "$VENV_DIR"`.

4. **TAREA-15: Registro de `websockets` y `Pillow`**
   - **Archivo:** `requirements.txt`
   - **Descripción:** Se añadieron las librerías necesarias para el funcionamiento del plugin OpenDeck a las dependencias oficiales del proyecto.

5. **TAREA-16: Dependencias en Post-instalador Debian**
   - **Archivo:** `packaging/build_deb.sh`
   - **Descripción:** Se incorporaron `textual`, `numpy`, `websockets` y `Pillow` en las llamadas a `uv pip` / `pip` del script `postinst`.

6. **TAREA-17: Creación de Entorno Virtual en Paquete Arch**
   - **Archivo:** `packaging/build_arch.sh`
   - **Descripción:** Se implementó la inicialización de `uv venv` e instalación de requerimientos dentro de la función `post_install()` del script de instalación de pacman.

7. **TAREA-18: Limpieza de Plugin Omarchy Shell en Desinstalación**
   - **Archivo:** `uninstall.sh`
   - **Descripción:** Se añadió la rutina para eliminar la carpeta del plugin visual en `~/.config/omarchy/plugins/com.kirulab.opendictate` y desvincular la entrada correspondencia en `shell.json`.

8. **TAREA-19: Uso de Python del VENV en Plugin Stream Deck**
   - **Archivo:** `plugins/com.kirulab.opendictate.sdplugin/start.sh`
   - **Descripción:** Se actualizó la invocación para detectar y utilizar el intérprete Python del entorno virtual local o del sistema antes de caer a `python3` global.

9. **TAREA-20: Inclusión de `~/.local/bin` en PATH tras Instalar `uv`**
   - **Archivo:** `install.sh`
   - **Descripción:** Se actualizó `export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"` para garantizar el acceso al ejecutable `uv` sin importar la ruta de instalación.

---

## Verificación de Sintaxis

Se ejecutó la verificación de sintaxis sobre todos los scripts bash modificados:
```bash
bash -n install.sh && bash -n uninstall.sh && bash -n packaging/build_deb.sh && bash -n packaging/build_arch.sh && bash -n plugins/com.kirulab.opendictate.sdplugin/start.sh
```
Resultado: Sintaxis 100% limpia.
