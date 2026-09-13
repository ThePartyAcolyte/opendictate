with open("CHANGELOG.md", "r") as f:
    lines = f.readlines()

new_entry = """## [Unreleased] - 2026-09-04

### Added
- **Herder Workspace Integration**: Implemented exact-tab focus recovery for the Herder ecosystem (`omarchy: wang-kapawu`). When dictation is initiated from a terminal pane running Herder, OpenDictate captures the exact `workspace_id` and `tab_id` from the active process environment or socket snapshot.
- **Robust Herder Window Detection**: `core/window_utils.py` now deeply inspects the Hyprland active window process tree (`pstree -T -p <pid>`) to unequivocally detect `herdr` background instances, preventing false positives from generic `ghostty` terminal sessions.
- **Seamless Tab Focus Restoration**: Upon paste execution (`_do_paste`), the daemon fires synchronous socket commands (`herdr workspace focus` and `herdr tab focus`) to restore the original Herder tab context instantly before sending `Ctrl+Shift+V`, guaranteeing agent commands are injected into the correct terminal session.

"""

for i, line in enumerate(lines):
    if line.startswith("## ["):
        lines.insert(i, new_entry)
        break

with open("CHANGELOG.md", "w") as f:
    f.writelines(lines)
