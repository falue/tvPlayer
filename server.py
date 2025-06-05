import asyncio
import websockets
import json
import threading
from flask import Flask, send_from_directory
import os
import subprocess
import signal
import sys

# --- CONFIG ---
WEB_DIR = os.path.abspath("./webremote")
SSID = "tvPlayer"
PASSWORD = "1234"  # leave blank for open network
INTERFACE = "wlan0"

# --- STATE ---
clients = set()
state = {"counter": 0}
app = Flask(__name__, static_folder=WEB_DIR)

# --- FLASK ROUTES ---
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(WEB_DIR, path)

# --- ACCESS POINT SETUP ---
def start_access_point():
    if PASSWORD:
        print(f"[AP] Starting secured hotspot '{SSID}'")
        subprocess.run([
            "nmcli", "dev", "wifi", "hotspot",
            "ifname", INTERFACE,
            "ssid", SSID,
            "password", PASSWORD
        ], check=True)
    else:
        print(f"[AP] Starting open hotspot '{SSID}'")
        subprocess.run([
            "nmcli", "connection", "add",
            "type", "wifi",
            "ifname", INTERFACE,
            "con-name", "OpenHotspot",
            "autoconnect", "no",
            "ssid", SSID
        ], check=True)
        subprocess.run([
            "nmcli", "connection", "modify", "OpenHotspot",
            "802-11-wireless.mode", "ap",
            "802-11-wireless.band", "bg",
            "ipv4.method", "shared",
            "802-11-wireless-security.key-mgmt", "none"
        ], check=True)
        subprocess.run([
            "nmcli", "connection", "up", "OpenHotspot"
        ], check=True)

def stop_access_point():
    if PASSWORD:
        subprocess.run(["nmcli", "connection", "down", "Hotspot"], stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["nmcli", "connection", "down", "OpenHotspot"], stderr=subprocess.DEVNULL)
        subprocess.run(["nmcli", "connection", "delete", "OpenHotspot"], stderr=subprocess.DEVNULL)

# --- WEBSOCKET HANDLER ---
async def ws_handler(ws):
    clients.add(ws)
    try:
        await ws.send(json.dumps(state))
        async for msg in ws:
            data = json.loads(msg)
            if data.get("command") == "increment":
                state["counter"] += 1
                print("[server] HTML increment:", state["counter"])
                await broadcast()
            elif data.get("from") == "tvPlayer":
                print("[server] Received from tvPlayer:", data)
                await broadcast()
    finally:
        clients.discard(ws)

async def broadcast():
    msg = json.dumps(state)
    await asyncio.gather(*(c.send(msg) for c in clients if not c.closed), return_exceptions=True)

# --- SERVER START ---
def start_flask():
    app.run(host="0.0.0.0", port=8080)

def start_websocket():
    async def serve_ws():
        async with websockets.serve(ws_handler, "0.0.0.0", 8765):
            await asyncio.Future()  # run forever

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(serve_ws())

# --- ENTRY POINT ---
def cleanup(sig=None, frame=None):
    print("\n[server] Cleaning up...")
    stop_access_point()
    sys.exit(0)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Run this script as root (use sudo)")
        sys.exit(1)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    start_access_point()

    threading.Thread(target=start_flask, daemon=True).start()
    start_websocket()
