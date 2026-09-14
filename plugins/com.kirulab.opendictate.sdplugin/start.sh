#!/bin/bash
VENV_PYTHON="$HOME/.local/share/opendictate/.venv/bin/python"
if [ -f "/opt/opendictate/.venv/bin/python" ]; then
    VENV_PYTHON="/opt/opendictate/.venv/bin/python"
fi

if [ -f "$VENV_PYTHON" ]; then
    "$VENV_PYTHON" plugin.py "$@"
else
    python3 plugin.py "$@"
fi
