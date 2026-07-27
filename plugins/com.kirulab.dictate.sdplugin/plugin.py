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
from PIL import Image, ImageDraw
import logging

logging.basicConfig(filename='/tmp/dictate_plugin.log', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s: %(message)s')
import io
import base64

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
    "send": set(),
    "preview": set(),
    "cancel": set(),
    "ai": set(),
    "autosend": set(),
    "autopause": set(),
    "bubble": set(),
    "realtime": set()
}

force_update = False

STATE_FILE = "/tmp/dictate_state.json"

def get_daemon_state():
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
        if current_state == "RECORDING":
            title = current_time
        elif current_state == "PAUSED":
            title = f"Paused\n{current_time}"
        elif current_state == "TRANSCRIBING":
            title = "Thinking..."
        elif current_state == "CLEANING":
            title = "AI Cleanup"
        elif current_state == "IDLE":
            title = model
        elif current_state == "LOADING":
            title = f"Loading\n{model}"
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
            for ctx in active_contexts["record"].copy():
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
            for ctx in active_contexts["send"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": send_usable}
                }))
            for ctx in active_contexts["preview"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": send_usable}
                }))
            for ctx in active_contexts["cancel"].copy():
                await ws.send(json.dumps({
                    "event": "setState",
                    "context": ctx,
                    "payload": {"state": send_usable}
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
            
            if event == "willAppear":
                global force_update
                force_update = True
                act_suffix = action.split(".")[-1]
                if act_suffix == "monitor":
                    active_contexts["monitor"].add(context)
                elif act_suffix == "record":
                    active_contexts["record"].add(context)
                elif act_suffix == "send":
                    active_contexts["send"].add(context)

                elif act_suffix == "preview":
                    active_contexts["preview"].add(context)
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
                    
                if act_suffix == "record":
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
                    if current_state == "RECORDING":
                        title = current_time
                    elif current_state == "PAUSED":
                        title = f"Paused\n{current_time}"
                    elif current_state == "TRANSCRIBING":
                        title = "Thinking..."
                    elif current_state == "CLEANING":
                        title = "AI Cleanup"
                    elif current_state == "IDLE":
                        title = model
                    elif current_state == "LOADING":
                        title = f"Loading\n{model}"
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
                    cancel_usable = 1 if current_state in ["RECORDING", "PAUSED", "TRANSCRIBING"] else 0
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
                elif act_suffix == "send" and context in active_contexts["send"]:
                    active_contexts["send"].remove(context)
                elif act_suffix == "preview" and context in active_contexts["preview"]:
                    active_contexts["preview"].remove(context)
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

            elif event == "keyUp":
                act_suffix = action.split(".")[-1]
                logging.debug(f"keyUp received for {act_suffix}")
                if act_suffix == "record":
                    state_data = get_daemon_state()
                    logging.debug(f"Current daemon state: {state_data.get('state')}")
                    if state_data.get("state") == "RECORDING":
                        subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--pause"])
                    else:
                        subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--record"])
                elif act_suffix == "monitor":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--cycle-model"])
                elif act_suffix == "send":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--send"])
                elif act_suffix == "preview":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--preview"])
                elif act_suffix == "cancel":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--cancel"])
                elif act_suffix == "toggle_ai":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--toggle-ai"])
                elif act_suffix == "toggle_autosend":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--toggle-autosend"])
                elif act_suffix == "toggle_autopause":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--toggle-autopause"])
                elif act_suffix == "toggle_bubble":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--toggle-bubble"])
                elif act_suffix == "toggle_realtime":
                    subprocess.Popen(["/home/butcherwutcher/.local/bin/dictate", "--toggle-realtime"])

if __name__ == "__main__":
    if port:
        asyncio.run(connect_streamdeck())
