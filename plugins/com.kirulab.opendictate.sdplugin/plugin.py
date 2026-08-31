"""Stream Deck and OpenDeck WebSocket bridge plugin for OpenDictate.

Handles rotary encoder gestures (clicks, double taps, long presses, dialing)
and standard hardware buttons, syncing daemon state in real-time.
"""

import sys
import json
import asyncio
import websockets
import subprocess
import os
import signal
import base64
import time
import math
import shutil
from PIL import Image, ImageDraw
import logging

logging.basicConfig(filename='/tmp/opendictate_plugin.log', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s: %(message)s')
import io
import base64

CLI_BIN = shutil.which("opendictate") or os.path.expanduser("~/.local/bin/opendictate")

# Stream Deck SDK arguments
port = None
pluginUUID = None
registerEvent = None
info = None

for i in range(len(sys.argv)):
    if sys.argv[i] == "-port":
        port = sys.argv[i + 1]
    elif sys.argv[i] == "-pluginUUID":
        pluginUUID = sys.argv[i + 1]
    elif sys.argv[i] == "-registerEvent":
        registerEvent = sys.argv[i + 1]
    elif sys.argv[i] == "-info":
        info = sys.argv[i + 1]

# Action context tracking
active_contexts = {
    "monitor": set(),
    "record": set(),
    "record_encoder": set(),
    "send": set(),
    "cancel": set(),
    "ai": set(),
    "autosend": set(),
    "autopause": set(),
    "bubble": set(),
    "realtime": set()
}

encoder_accumulators = {}
encoder_settings = {}
long_press_tasks = {}
long_press_triggered = {}
double_tap_tasks = {}
double_tap_counts = {}

def execute_primary_action():
    """Execute primary record / pause toggle action via OpenDictate CLI."""
    state_data = get_daemon_state()
    logging.debug(f"Executing primary action, daemon state: {state_data.get('state')}")
    if state_data.get("state") == "RECORDING":
        subprocess.Popen([CLI_BIN, "--pause"])
    else:
        subprocess.Popen([CLI_BIN, "--record"])

async def execute_secondary_action(ws, action_type, profile, dev_id):
    """Execute secondary encoder gesture action (open settings or switch Stream Deck profile).

    Args:
        ws: OpenDeck WebSocket connection.
        action_type: Configured action ('settings' or 'switch_profile').
        profile: Target profile name if action is 'switch_profile'.
        dev_id: Stream Deck hardware device identifier.
    """
    logging.debug(f"Executing secondary action: {action_type}")
    if action_type == "settings":
        subprocess.Popen([CLI_BIN, "--settings"])
    elif action_type == "switch_profile":
        if profile:
            await ws.send(json.dumps({
                "event": "switchToProfile",
                "context": pluginUUID,
                "device": dev_id,
                "payload": {
                    "profile": profile,
                    "page": profile
                }
            }))

def update_encoder_settings(context, settings):
    """Parse and cache Property Inspector settings for a given encoder context.

    Args:
        context: Unique action context string.
        settings: Settings dictionary received from OpenDeck Property Inspector.
    """
    if not settings:
        return
    current = encoder_settings.get(context, {})
    if not isinstance(current, dict):
        current = {}
    threshold = int(settings.get("threshold", current.get("threshold", 3)))
    
    sec_mode = settings.get("secondaryTriggerMode")
    if not sec_mode:
        old_lp = settings.get("longPressAction", current.get("secondary_action", "none"))
        if old_lp == "none":
            sec_mode = "disabled"
            sec_action = "settings"
        else:
            sec_mode = "long_press"
            sec_action = old_lp
    else:
        sec_action = settings.get("secondaryAction", current.get("secondary_action", "settings"))

    target_profile = settings.get("targetProfile", current.get("target_profile", ""))
    dt_window = float(settings.get("doubleTapWindow", current.get("double_tap_window", 300))) / 1000.0
    lp_duration = float(settings.get("longPressDuration", current.get("long_press_duration", 1000))) / 1000.0
    
    encoder_settings[context] = {
        "threshold": threshold,
        "secondary_mode": sec_mode,
        "secondary_action": sec_action,
        "target_profile": target_profile,
        "double_tap_window": dt_window,
        "long_press_duration": lp_duration
    }

force_update = False

STATE_FILE = "/tmp/opendictate_state.json"

def get_daemon_state():
    """Read latest daemon telemetry exported to /tmp/opendictate_state.json.

    Returns:
        Dictionary containing state, model, level, and toggle flags.
    """
    for _ in range(3):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            time.sleep(0.05)
            continue
    return {
        "state": "OFFLINE", 
        "time_str": "00:00", 
        "model": "", 
        "level": 0.0,
        "ai_enabled": False,
        "autosend_enabled": False,
        "autopause_enabled": True,
        "hide_bubble": False,
        "send_status": "idle"
    }

def generate_progress_image(level, phase):
    """Generate dynamic base64 PNG icon with audio level meter or processing animation.

    Args:
        level: Normalized audio energy float [0.0, 1.0].
        phase: Current daemon phase string (e.g. 'RECORDING', 'TRANSCRIBING', 'CLEANING').

    Returns:
        Base64-encoded data URI string for Stream Deck setImage event.
    """
    img = Image.new('RGB', (72, 72), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)
    
    t = int(time.time() * 1000)
    
    if phase == "RECORDING":
        h = int(level * 72)
        draw.rectangle([0, 72-h, 72, 72], fill=(200, 50, 50))
    elif phase == "TRANSCRIBING":
        # pulsing width
        w = int((math.sin(t / 200.0) + 1) / 2 * 72)
        draw.rectangle([0, 62, w, 72], fill=(50, 150, 250))
    elif phase == "CLEANING":
        w = int((math.sin(t / 200.0) + 1) / 2 * 72)
        draw.rectangle([0, 62, w, 72], fill=(150, 50, 200))
        
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_str}"

async def watch_state(ws):
    """Asynchronous background loop pushing live daemon state and audio meters to Stream Deck.

    Args:
        ws: OpenDeck WebSocket connection.
    """
    last_state = None
    last_time = None
    last_level = None
    
    while True:
        state_data = get_daemon_state()
        current_state = state_data.get("state", "OFFLINE")
        current_time = state_data.get("time_str", "00:00")
        model = state_data.get("model", "")
        level = state_data.get("level", 0.0)
        ai_enabled = state_data.get("ai_enabled", False)
        autosend_enabled = state_data.get("autosend_enabled", False)
        autopause_enabled = state_data.get("autopause_enabled", True)
        hide_bubble = state_data.get("hide_bubble", False)
        
        # State mapping for the record button (0: Idle, 1: Recording, 2: Paused)
        state_idx = 0
        if current_state == "RECORDING":
            state_idx = 1
        elif current_state == "PAUSED":
            state_idx = 2
            
        # Title formatting
        title = ""
        global force_update
        status_text = state_data.get("status_text")
        if current_state == "RECORDING":
            title = current_time
        elif current_state == "PAUSED":
            title = f"Paused\n{current_time}"
        elif current_state in ["TRANSCRIBING", "CLEANING", "PROCESSING"]:
            title = status_text if status_text else ("Thinking..." if current_state == "TRANSCRIBING" else "AI Cleanup")
        elif current_state == "IDLE":
            title = model
        elif current_state == "LOADING":
            title = status_text if status_text else f"Loading\n{model}"
        else:
            title = "Offline"
            
        changed = False
        if current_state != last_state or current_time != last_time or force_update:
            changed = True
            force_update = False
            last_state = current_state
            last_time = current_time
            
        needs_animation = current_state in ["RECORDING", "TRANSCRIBING", "CLEANING"]
        
        if changed:
            # Update Record buttons (only when state changes)
            for ctx in active_contexts["record"].union(active_contexts["record_encoder"]):
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": state_idx}
                }))
                await ws.send(json.dumps({
                    "event": "setTitle",
                    "context": ctx,
                    "payload": {"title": "", "target": 0}
                }))
                
            # Update toggles
            for ctx in active_contexts["ai"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": 1 if ai_enabled else 0}
                }))
                
            for ctx in active_contexts["autosend"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": 1 if autosend_enabled else 0}
                }))
                
            for ctx in active_contexts["autopause"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": 1 if autopause_enabled else 0}
                }))
                
            # Update Send and Cancel states
            send_usable = 1 if current_state in ["RECORDING", "PAUSED"] else 0
            cancel_usable = 1 if current_state in ["RECORDING", "PAUSED", "TRANSCRIBING", "CLEANING", "PROCESSING", "LOADING"] else 0
            for ctx in active_contexts["send"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": send_usable}
                }))
            for ctx in active_contexts["cancel"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": cancel_usable}
                }))
                
            for ctx in active_contexts["bubble"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": 0 if hide_bubble else 1}
                }))
                
            realtime_enabled = state_data.get("realtime_enabled", True)
            for ctx in active_contexts["realtime"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": 1 if realtime_enabled else 0}
                }))

        if changed or needs_animation:
            # Generate animated background
            img_b64 = generate_progress_image(level, current_state)
            
            # Update Monitor buttons
            for ctx in active_contexts["monitor"].copy():
                await ws.send(json.dumps({
                    "event": "setImage",
                    "context": ctx,
                    "payload": {"image": img_b64, "target": 0}
                }))
                # It's okay to send title repeatedly
                await ws.send(json.dumps({
                    "event": "setTitle",
                    "context": ctx,
                    "payload": {"title": title, "target": 0}
                }))
                
        await asyncio.sleep(0.1)

async def connect_streamdeck():
    uri = f"ws://127.0.0.1:{port}"
    async with websockets.connect(uri) as ws:
        # Register plugin
        await ws.send(json.dumps({
            "event": registerEvent,
            "uuid": pluginUUID
        }))
        
        # Start state watcher task
        asyncio.create_task(watch_state(ws))
        
        # Listen for events
        async for message in ws:
            data = json.loads(message)
            event = data.get("event")
            context = data.get("context")
            action = data.get("action")
            payload = data.get("payload", {})
            
            if event == "willAppear":
                global force_update
                force_update = True
                
                settings = payload.get("settings", {})
                update_encoder_settings(context, settings)

                act_suffix = action.split(".")[-1]
                if act_suffix == "monitor":
                    active_contexts["monitor"].add(context)
                elif act_suffix == "record":
                    active_contexts["record"].add(context)
                elif act_suffix == "record_encoder":
                    active_contexts["record_encoder"].add(context)
                elif act_suffix == "send":
                    active_contexts["send"].add(context)
                elif act_suffix == "cancel":
                    active_contexts["cancel"].add(context)
                elif act_suffix == "toggle_ai":
                    active_contexts["ai"].add(context)
                elif act_suffix == "toggle_autosend":
                    active_contexts["autosend"].add(context)
                elif act_suffix == "toggle_autopause":
                    active_contexts["autopause"].add(context)
                elif act_suffix == "toggle_bubble":
                    active_contexts["bubble"].add(context)
                elif act_suffix == "toggle_realtime":
                    active_contexts["realtime"].add(context)
                    
                # Force immediate update for new buttons
                state_data = get_daemon_state()
                current_state = state_data.get("state", "OFFLINE")
                current_time = state_data.get("time_str", "00:00")
                model = state_data.get("model", "")
                level = state_data.get("level", 0.0)
                ai_enabled = state_data.get("ai_enabled", False)
                autosend_enabled = state_data.get("autosend_enabled", False)
                autopause_enabled = state_data.get("autopause_enabled", True)
                hide_bubble = state_data.get("hide_bubble", False)
                realtime_enabled = state_data.get("realtime_enabled", True)
                
                state_idx = 0
                if current_state == "RECORDING":
                    state_idx = 1
                elif current_state == "PAUSED":
                    state_idx = 2
                    
                if act_suffix in ["record", "record_encoder"]:
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": state_idx}
                    })))
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setTitle",
                        "context": context,
                        "payload": {"title": "", "target": 0}
                    })))
                elif act_suffix == "monitor":
                    title = ""
                    status_text = state_data.get("status_text")
                    if current_state == "RECORDING":
                        title = current_time
                    elif current_state == "PAUSED":
                        title = f"Paused\n{current_time}"
                    elif current_state in ["TRANSCRIBING", "CLEANING", "PROCESSING"]:
                        title = status_text if status_text else ("Thinking..." if current_state == "TRANSCRIBING" else "AI Cleanup")
                    elif current_state == "IDLE":
                        title = model
                    elif current_state == "LOADING":
                        title = status_text if status_text else f"Loading\n{model}"
                    else:
                        title = "Offline"
                        
                    img_b64 = generate_progress_image(level, current_state)
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setImage",
                        "context": context,
                        "payload": {"image": img_b64, "target": 0}
                    })))
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setTitle",
                        "context": context,
                        "payload": {"title": title, "target": 0}
                    })))
                elif act_suffix == "toggle_ai":
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": 1 if ai_enabled else 0}
                    })))
                elif act_suffix == "toggle_autosend":
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": 1 if autosend_enabled else 0}
                    })))
                elif act_suffix == "toggle_autopause":
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": 1 if autopause_enabled else 0}
                    })))
                elif act_suffix == "toggle_bubble":
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": 0 if hide_bubble else 1}
                    })))
                elif act_suffix == "toggle_realtime":
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": 1 if realtime_enabled else 0}
                    })))
                elif act_suffix == "send":
                    send_usable = 1 if current_state in ["RECORDING", "PAUSED"] else 0
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": send_usable}
                    })))
                elif act_suffix == "preview":
                    send_usable = 1 if current_state in ["RECORDING", "PAUSED"] else 0
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": send_usable}
                    })))
                elif act_suffix == "cancel":
                    cancel_usable = 1 if current_state in ["RECORDING", "PAUSED", "TRANSCRIBING", "CLEANING", "PROCESSING", "LOADING"] else 0
                    asyncio.create_task(ws.send(json.dumps({
                        "event": "setState",
                        "context": context,
                        "payload": {"state": cancel_usable}
                    })))

            elif event == "willDisappear":
                act_suffix = action.split(".")[-1]
                if act_suffix == "monitor" and context in active_contexts["monitor"]:
                    active_contexts["monitor"].remove(context)
                elif act_suffix == "record" and context in active_contexts["record"]:
                    active_contexts["record"].remove(context)
                elif act_suffix == "record_encoder" and context in active_contexts["record_encoder"]:
                    active_contexts["record_encoder"].remove(context)
                elif act_suffix == "send" and context in active_contexts["send"]:
                    active_contexts["send"].remove(context)
                elif act_suffix == "cancel" and context in active_contexts["cancel"]:
                    active_contexts["cancel"].remove(context)
                elif act_suffix == "toggle_ai" and context in active_contexts["ai"]:
                    active_contexts["ai"].remove(context)
                elif act_suffix == "toggle_autosend" and context in active_contexts["autosend"]:
                    active_contexts["autosend"].remove(context)
                elif act_suffix == "toggle_autopause" and context in active_contexts["autopause"]:
                    active_contexts["autopause"].remove(context)
                elif act_suffix == "toggle_bubble" and context in active_contexts["bubble"]:
                    active_contexts["bubble"].remove(context)
                elif act_suffix == "toggle_realtime" and context in active_contexts["realtime"]:
                    active_contexts["realtime"].remove(context)

                if context in long_press_tasks:
                    long_press_tasks[context].cancel()
                    del long_press_tasks[context]
                if context in long_press_triggered:
                    del long_press_triggered[context]
                if context in double_tap_tasks:
                    double_tap_tasks[context].cancel()
                    del double_tap_tasks[context]
                if context in double_tap_counts:
                    del double_tap_counts[context]

            elif event == "didReceiveSettings":
                settings = payload.get("settings", {})
                update_encoder_settings(context, settings)

            elif event in ["keyDown", "dialDown"]:
                act_suffix = action.split(".")[-1]
                logging.debug(f"{event} received for {act_suffix}")
                if act_suffix in ["record", "record_encoder"]:
                    cfg = encoder_settings.get(context, {})
                    if isinstance(cfg, dict):
                        sec_mode = cfg.get("secondary_mode", "disabled")
                        sec_action = cfg.get("secondary_action", "settings")
                        target_prof = cfg.get("target_profile", "")
                        lp_delay = cfg.get("long_press_duration", 1.0)
                    else:
                        sec_mode = "disabled"
                        sec_action = "settings"
                        target_prof = ""
                        lp_delay = 1.0
                    device_id = data.get("device", "")

                    if sec_mode == "long_press":
                        long_press_triggered[context] = False

                        async def _long_press_timer(ctx=context, action_type=sec_action, profile=target_prof, duration=lp_delay, dev=device_id):
                            try:
                                await asyncio.sleep(duration)
                                long_press_triggered[ctx] = True
                                logging.debug(f"Long press triggered for {ctx}: {action_type}")
                                await execute_secondary_action(ws, action_type, profile, dev)
                            except asyncio.CancelledError:
                                pass

                        if context in long_press_tasks:
                            long_press_tasks[context].cancel()
                        long_press_tasks[context] = asyncio.create_task(_long_press_timer())

            elif event in ["keyUp", "dialUp"]:
                act_suffix = action.split(".")[-1]
                logging.debug(f"{event} received for {act_suffix}")
                if act_suffix in ["record", "record_encoder"]:
                    cfg = encoder_settings.get(context, {})
                    if isinstance(cfg, dict):
                        sec_mode = cfg.get("secondary_mode", "disabled")
                        sec_action = cfg.get("secondary_action", "settings")
                        target_prof = cfg.get("target_profile", "")
                        dt_win = cfg.get("double_tap_window", 0.3)
                    else:
                        sec_mode = "disabled"
                        sec_action = "settings"
                        target_prof = ""
                        dt_win = 0.3
                    device_id = data.get("device", "")

                    if sec_mode == "long_press":
                        if context in long_press_tasks:
                            long_press_tasks[context].cancel()
                            del long_press_tasks[context]

                        if long_press_triggered.get(context, False):
                            long_press_triggered[context] = False
                            logging.debug(f"Long press handled for {context}, skipping short press")
                        else:
                            execute_primary_action()

                    elif sec_mode == "double_tap":
                        count = double_tap_counts.get(context, 0) + 1
                        double_tap_counts[context] = count
                        logging.debug(f"Double tap count for {context}: {count}")

                        if count == 1:
                            async def _double_tap_timer(ctx=context, window=dt_win):
                                try:
                                    await asyncio.sleep(window)
                                    if double_tap_counts.get(ctx, 0) == 1:
                                        logging.debug(f"Double tap window expired for {ctx}, executing primary action")
                                        execute_primary_action()
                                    double_tap_counts[ctx] = 0
                                    if ctx in double_tap_tasks:
                                        del double_tap_tasks[ctx]
                                except asyncio.CancelledError:
                                    pass

                            if context in double_tap_tasks:
                                double_tap_tasks[context].cancel()
                            double_tap_tasks[context] = asyncio.create_task(_double_tap_timer())

                        elif count >= 2:
                            if context in double_tap_tasks:
                                double_tap_tasks[context].cancel()
                                del double_tap_tasks[context]
                            double_tap_counts[context] = 0
                            logging.debug(f"Double tap triggered for {context}: {sec_action}")
                            asyncio.create_task(execute_secondary_action(ws, sec_action, target_prof, device_id))

                    else:
                        execute_primary_action()
                elif act_suffix == "monitor":
                    subprocess.Popen([CLI_BIN, "--cycle-model"])
                elif act_suffix == "send":
                    subprocess.Popen([CLI_BIN, "--send"])
                elif act_suffix == "cancel":
                    subprocess.Popen([CLI_BIN, "--cancel"])
                elif act_suffix == "toggle_ai":
                    subprocess.Popen([CLI_BIN, "--toggle-ai"])
                elif act_suffix == "toggle_autosend":
                    subprocess.Popen([CLI_BIN, "--toggle-autosend"])
                elif act_suffix == "toggle_autopause":
                    subprocess.Popen([CLI_BIN, "--toggle-autopause"])
                elif act_suffix == "toggle_bubble":
                    subprocess.Popen([CLI_BIN, "--toggle-bubble"])
                elif act_suffix == "toggle_realtime":
                    subprocess.Popen([CLI_BIN, "--toggle-realtime"])

            elif event == "dialRotate":
                act_suffix = action.split(".")[-1]
                ticks = payload.get("ticks", 1)
                if act_suffix == "record_encoder":
                    now = time.time()
                    state = encoder_accumulators.setdefault(context, {"ticks": 0, "last_time": 0.0})
                    cfg = encoder_settings.get(context, {})
                    threshold = cfg.get("threshold", 3) if isinstance(cfg, dict) else 3
                    
                    if now - state["last_time"] > 0.5:
                        state["ticks"] = 0
                        
                    state["ticks"] += ticks
                    state["last_time"] = now
                    
                    if state["ticks"] >= threshold:
                        subprocess.Popen([CLI_BIN, "--send"])
                        state["ticks"] = 0
                    elif state["ticks"] <= -threshold:
                        subprocess.Popen([CLI_BIN, "--cancel"])
                        state["ticks"] = 0

if __name__ == "__main__":
    if port:
        asyncio.run(connect_streamdeck())
