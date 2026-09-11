"""
HDMI connector manager for tvPlayer.

Auto-discovers HDMI connectors via /sys/class/drm/,
selects the preferred one (HDMI-A-1 > HDMI-A-2),
and monitors for hotplug changes.

Priority:
  - HDMI-A-1 (physical HDMI0, next to USB-C power) preferred
  - HDMI-A-2 (physical HDMI1, next to audio jack) fallback

When the preferred connector state changes, triggers a clean restart
via os._exit(75) so systemd restarts the service on the new output.
"""

import os
import threading
import time
from pathlib import Path
import mqtt_handler

DRM_BASE = Path("/sys/class/drm")
PREFERRED_CONNECTOR = "HDMI-A-1"
FALLBACK_CONNECTOR = "HDMI-A-2"
POLL_INTERVAL = 1.0  # seconds

ACTIVE_CONNECTOR = None  # set by choose_connector()
_states = {}  # cached connector states, only written by the monitor thread


def get_states():
    """
    Cached state of every HDMI connector, for the MQTT heartbeat.
    Does no filesystem access — the monitor thread keeps this up to date.
    Returns: {"HDMI-A-1": {"connected": bool, "active": bool}, ..}
    """
    return _states


def _set_states(connected_map):
    """Refresh the cache from a {name: bool} map."""
    global _states
    _states = {
        name: {"connected": connected, "active": name == ACTIVE_CONNECTOR}
        for name, connected in connected_map.items()
    }


def discover_connectors():
    """
    Scan /sys/class/drm/ for HDMI connector entries.
    Returns dict: {"HDMI-A-1": "/sys/class/drm/card1-HDMI-A-1", ...}
    """
    connectors = {}
    if not DRM_BASE.exists():
        return connectors
    for entry in DRM_BASE.iterdir():
        name = entry.name
        # Entries look like: card1-HDMI-A-1, card0-HDMI-A-2, etc.
        if "HDMI-A-1" in name:
            connectors["HDMI-A-1"] = entry
        elif "HDMI-A-2" in name:
            connectors["HDMI-A-2"] = entry
    return connectors


def is_connected(connector_path):
    """Check if a connector has a display attached."""
    status_file = connector_path / "status"
    try:
        return status_file.read_text().strip() == "connected"
    except Exception:
        return False


def choose_connector():
    """
    Choose the best available HDMI connector.
    Prefers HDMI-A-1, falls back to HDMI-A-2.
    Returns the connector name string for mpv's drm-connector option,
    or None if no connectors found.
    """
    global ACTIVE_CONNECTOR

    connectors = discover_connectors()
    if not connectors:
        print("[HDMI] No HDMI connectors found in /sys/class/drm/")
        return None

    if PREFERRED_CONNECTOR in connectors and is_connected(connectors[PREFERRED_CONNECTOR]):
        print(f"[HDMI] Using preferred connector: {PREFERRED_CONNECTOR}")
        ACTIVE_CONNECTOR = PREFERRED_CONNECTOR
    elif FALLBACK_CONNECTOR in connectors:
        if is_connected(connectors[FALLBACK_CONNECTOR]):
            print(f"[HDMI] Using fallback connector: {FALLBACK_CONNECTOR}")
        else:
            print(f"[HDMI] No display detected, starting on: {FALLBACK_CONNECTOR}")
        ACTIVE_CONNECTOR = FALLBACK_CONNECTOR
    elif PREFERRED_CONNECTOR in connectors:
        # Only preferred exists but not connected — use it anyway
        print(f"[HDMI] No display detected, starting on: {PREFERRED_CONNECTOR}")
        ACTIVE_CONNECTOR = PREFERRED_CONNECTOR
    else:
        return None

    # Seed the cache so the heartbeat has data before the first poll
    _set_states({name: is_connected(path) for name, path in connectors.items()})

    return ACTIVE_CONNECTOR


def report_state(connector, connected, active_connector):
    """
    Print and publish the state of a single connector so the webremote
    can keep its status badges accurate.
    """
    state = "connected" if connected else "disconnected"
    active = " (active)" if connector == active_connector else ""
    msg = f"[HDMI] {connector} {state}{active}"
    print(msg)
    mqtt_handler.send("general", msg)


def start_hotplug_monitor(active_connector, on_exit_cleanup=None):
    """
    Start a daemon thread that polls connector states.
    Triggers os._exit(75) when the preferred connector state changes
    (i.e. HDMI-A-1 gets plugged in while on HDMI-A-2, or HDMI-A-1
    gets unplugged while active).

    Args:
        active_connector: The connector currently in use (e.g. "HDMI-A-2")
        on_exit_cleanup: Optional callable to run before exit (save settings, GPIO cleanup)
    """
    connectors = discover_connectors()
    if not connectors:
        print("[HDMI] No connectors to monitor, hotplug disabled.")
        return

    def monitor():
        # Track last known state of every discovered connector
        was_connected = {name: is_connected(path) for name, path in connectors.items()}
        _set_states(was_connected)

        while True:
            time.sleep(POLL_INTERVAL)

            now_connected = {name: is_connected(path) for name, path in connectors.items()}

            # Report every state change, whether or not it causes a restart
            changed = False
            for name, state in now_connected.items():
                if state != was_connected[name]:
                    report_state(name, state, active_connector)
                    changed = True

            if changed:
                _set_states(now_connected)

            preferred_was = was_connected.get(PREFERRED_CONNECTOR, False)
            preferred_now = now_connected.get(PREFERRED_CONNECTOR, False)

            should_restart = False

            if active_connector != PREFERRED_CONNECTOR and preferred_now and not preferred_was:
                # Preferred just got plugged in, switch to it
                msg = f"[HDMI] {PREFERRED_CONNECTOR} connected — switching output (Restart manually if started with 'python3 tvPlayer.py')"
                print(msg)
                mqtt_handler.send("general", msg)
                should_restart = True
            elif active_connector == PREFERRED_CONNECTOR and not preferred_now and preferred_was:
                # Preferred just got unplugged, fall back
                msg = f"[HDMI] {PREFERRED_CONNECTOR} disconnected — falling back to {FALLBACK_CONNECTOR}."
                print(msg)
                mqtt_handler.send("general", msg)
                should_restart = True

            if should_restart:
                if on_exit_cleanup:
                    try:
                        on_exit_cleanup()
                    except Exception as e:
                        print(f"[HDMI] Cleanup error: {e}")
                time.sleep(0.25)  # Let MQTT deliver the message
                os._exit(75)

            was_connected = now_connected

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    print(f"[HDMI] Hotplug monitor started (watching {PREFERRED_CONNECTOR}, polling every {POLL_INTERVAL}s)")
