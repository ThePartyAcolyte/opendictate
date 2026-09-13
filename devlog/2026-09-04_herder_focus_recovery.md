# Devlog: Herder Tab Focus Recovery Integration

**Date:** 2026-09-04  
**Topic:** Herder Workspace Integration, Window Process Tree Detection, Contextual Focus Restoration

## Overview
Implemented a robust focus restoration mechanism to ensure that text pasted by OpenDictate is injected precisely into the Herder tab and workspace that was active when dictation started. This prevents text from being injected into the wrong agent or pane if the user navigated away during dictation.

## Key Changes
1. **Unequivocal Herder Detection (`core/window_utils.py`)**:
   - Replaced generic terminal detection heuristics with a deep process tree inspection (`is_herder_window`).
   - By querying `hyprctl clients -j` to get the window's exact PID, we now run `pstree -T -p <pid>` to verify if `herdr` is a child process of that specific terminal window. This prevents false positives when standard `ghostty` terminal instances are active.

2. **Herder Context Capture (`get_herder_context`)**:
   - When a Herder window is detected at the start of a dictation session (`start_recording`), the daemon captures the active context.
   - It reads `HERDR_TAB_ID` and `HERDR_WORKSPACE_ID` environment variables.
   - Falls back to querying the blazingly fast local Unix socket via `herdr api snapshot` to extract `focused_tab_id` and `focused_workspace_id`.

3. **Restoration Protocol (`_do_paste` in `opendictate-daemon.py`)**:
   - Before emitting the `Ctrl+Shift+V` keystroke via `ydotool`/`wtype`, the daemon restores the main OS window focus via Hyprland.
   - Immediately afterward, it fires synchronous `herdr workspace focus` and `herdr tab focus` commands over the Herder socket.
   - This ensures the exact Herder tab (where the user initiated the voice session) is brought to the front, safely injecting text into the correct terminal agent pane.
