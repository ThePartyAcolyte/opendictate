import re

with open("core/window_utils.py", "r") as f:
    content = f.read()

new_functions = """
def is_herder_window(window_address: Optional[str]) -> bool:
    \"\"\"Unequivocally determine if a Hyprland window is running Herder by inspecting its process tree.
    
    Args:
        window_address: Hyprland/Wayland window memory address.
        
    Returns:
        True if herdr is a child process of the window, False otherwise.
    \"\"\"
    import json
    if not window_address or window_address == "unknown":
        return False
        
    hyprctl_path = shutil.which("hyprctl")
    if not hyprctl_path:
        return False
        
    try:
        res = subprocess.run([hyprctl_path, "clients", "-j"], capture_output=True, text=True, timeout=0.3)
        if res.returncode == 0 and res.stdout.strip():
            clients = json.loads(res.stdout)
            for c in clients:
                if c.get("address") == window_address:
                    pid = c.get("pid")
                    if pid:
                        # Check the process tree of this specific window for 'herdr'
                        pstree_res = subprocess.run(["pstree", "-T", "-p", str(pid)], capture_output=True, text=True, timeout=0.2)
                        if pstree_res.returncode == 0 and "herdr" in pstree_res.stdout:
                            return True
                    break
    except Exception as e:
        logging.debug(f"is_herder_window check failed: {e}")
        
    return False


def get_herder_context() -> Tuple[Optional[str], Optional[str]]:
    \"\"\"Retrieve the active Herder tab and workspace.
    
    Checks environment variables first, then queries the herdr socket via 'herdr api snapshot'.
    
    Returns:
        Tuple of (tab_id, workspace_id).
    \"\"\"
    import os, json
    
    # 1. Attempt from injected environment variables (if running inside Herder)
    tab_id = os.environ.get("HERDR_TAB_ID")
    ws_id = os.environ.get("HERDR_WORKSPACE_ID")
    if tab_id and ws_id:
        return tab_id, ws_id
        
    # 2. Query herdr api snapshot
    herdr_path = shutil.which("herdr")
    if herdr_path:
        try:
            res = subprocess.run([herdr_path, "api", "snapshot"], capture_output=True, text=True, timeout=0.5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                snapshot = data.get("result", {}).get("snapshot", {})
                tab_id = snapshot.get("focused_tab_id")
                ws_id = snapshot.get("focused_workspace_id")
                if tab_id and ws_id:
                    return tab_id, ws_id
        except Exception as e:
            logging.debug(f"herdr api snapshot failed: {e}")
            
    return None, None


def restore_herder_tab_focus(tab_id: str, workspace_id: str) -> bool:
    \"\"\"Attempt to restore focus to a specific Herder tab and workspace.
    
    Args:
        tab_id: Herder tab ID.
        workspace_id: Herder workspace ID.
        
    Returns:
        True if focus commands were executed successfully, False otherwise.
    \"\"\"
    herdr_path = shutil.which("herdr")
    if not herdr_path or not tab_id or not workspace_id:
        return False
        
    try:
        # 1. Focus workspace (if it's different it will switch)
        res_ws = subprocess.run([herdr_path, "workspace", "focus", workspace_id], capture_output=True, timeout=0.5)
        
        # 2. Focus exact tab
        res_tab = subprocess.run([herdr_path, "tab", "focus", tab_id], capture_output=True, timeout=0.5)
        
        if res_tab.returncode == 0:
            logging.info(f"Restored Herder context: workspace='{workspace_id}', tab='{tab_id}'")
            return True
    except Exception as e:
        logging.error(f"Error restoring Herder tab focus: {e}")
        
    return False

"""

if "def is_herder_window" not in content:
    content += "\n" + new_functions

with open("core/window_utils.py", "w") as f:
    f.write(content)
