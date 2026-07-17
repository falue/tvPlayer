import os
import sys
import subprocess
import threading
import json
import time
import pwd
from natsort import natsorted
import random
import RPi.GPIO as GPIO
import mqtt_handler
import traceback
import socket
import mpv
import select

# Customizing
show_tv_gui = True  # show number of channels top right and volume bar
show_whitenoise_channel_change = True  # white noise in between channel switching
white_noise_duration = 0.1  # duration which shows white noise when changing channels, in seconds
gui_display_duration = 2.0  # Duration of the gui numbers stays alive, minus the white_noise_duration, in seconds
tv_channel_offset = 1  # display higher channel nr than actually available

allowed_fileendings = (
    '.mp4', '.mkv', '.avi', '.mxf', '.mov', '.m4v',
    '.jpg', '.jpeg', '.png', '.gif', '.tiff', '.bmp'
)

# GPIO Pin Definitions
LED_PIN = 18  # GPIO pin for LED

# 2x 4-button-foil-keypad and one additinal push btn
# https://toptechboy.com/wp-content/uploads/2022/04/pinout-corrected.jpg
# "Shorting pins 5 (GPIO3) and 6 (GND) when shutdown should boot the Pi." => https://dreamonward.com/2019/11/20/on-off-button/
BUTTON_PINS = [4, 17, 27, 22, 5, 6, 13, 19, 3]  # GPIO pins for buttons

# Leave me be
window_width = 1920
window_height = 1080
tv_channel = 0
filelist = []
filelist_ignored = []
inpoints = []
outpoints = []
video_fittings = []
video_speeds = []
ignored_devices = []
player = None  # python-mpv player instance
fitting_modes = ['contain', 'stretch', 'cover']  # List of fitting modes
fill_color_type = "green"  # default
fill_color_index = {"green": 0, "black": 0, "noise": 0}
fill_color_max_index = {"green": 19, "black": 0, "noise": 3}  # Amount of files in assets/fill_color -1
fill_color_active = False
current_file = ""
pan_offsets = {'x': 0.0, 'y': 0.0, 'x-real': 0, 'y-real': 0}  # Global variables to track the pan offsets
has_av_channel = False
brightness = 0  # -100 to 100, default 0
contrast = 0  # -100 to 100, default 0
saturation = 0  # -100 to 100, default 0
volume = 100  # 0 to 100, 100 means max loudness
muted = False
active_overlays = {}  # Dictionary to store active overlay threads
last_sent_settings = 0
zoom_level = 0.0
_save_timer = None  # timer for saving after mqtt msg
quit_program_scheduled = False
restart_program_scheduled = False
evdev_thread = None

file_settings = {}
SETTINGS_FILE = "settings.json"
settings_lock = threading.Lock()
script_dir = os.path.dirname(os.path.abspath(__file__))

def mqtt_init():
    mqtt_handler.set_command_handler(handle_command)
    mqtt_handler.start()

def udp_init(port=9999):
    """
        Initialize UDP listener for commands
        Test with
        echo '{"command":"next_channel"}' | nc -u <pi-ip> 9999
    """
    def udp_listener():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        print(f"[UDP] Listening on port {port}")
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                payload = json.loads(data.decode())
                print(f"[UDP] From {addr}: {payload}")
                handle_command(payload)
            except Exception as e:
                print(f"[UDP] Error: {e}")
    threading.Thread(target=udp_listener, daemon=True).start()

def handle_command(data):
    global quit_program_scheduled, restart_program_scheduled
    # print("[tvPlayer] Command from MQTT:", data)

    cmd = data.get("command")
    value = data.get("value", 0)

    if cmd == "give_settings":
        # Collect settings and send it by mqtt
        send_settings()
    elif cmd == "toggle_play":
        toggle_play()
    elif cmd == "toggle_fullscreen":
        toggle_fullscreen()

    elif cmd == "jump":
        jump(float(value))
    elif cmd == "seek":  
        if value < 0.05 and value > -0.05:
            pause()
        seek(float(value))
    elif cmd == "next_channel":
        next_channel()
    elif cmd == "prev_channel":
        prev_channel()

    elif cmd == "set_video_fitting":
        set_video_fitting()

    elif cmd == "volume":
        adjust_volume(int(value))
    elif cmd == "toggle_mute":
        if muted:
            set_volume(volume)  # unmute to previous volume
        else:
            set_volume(0)  # mute!

    elif cmd == "pan_reset":  # adjust in html
        pan("reset", "x")
        pan("reset", "y")
    elif cmd == "pan":
        pan(*value)

    elif cmd == "brightness":
        adjust_video_brightness(int(value))
    elif cmd == "contrast":
        adjust_video_contrast(int(value))
    elif cmd == "saturation":
        adjust_video_saturation(int(value))

    elif cmd == "speed":
        if value == "reset":
            adjust_video_speed(value)
        else:
            adjust_video_speed(float(value))

    # Fill colors
    elif cmd == "toggle_black_screen":
        toggle_fill_color("black")
    elif cmd == "cycle_green_screen":
        select_fill_color(int(value), "green")
    elif cmd == "toggle_green_screen":
        toggle_fill_color("green")
    elif cmd == "cycle_white_noise":
        select_fill_color(int(value), "noise")
    elif cmd == "toggle_white_noise":
        toggle_fill_color("noise")

    elif cmd == "set_inpoint":
        set_inpoint(tv_channel)
    elif cmd == "clear_inpoint":
        clear_inpoint(tv_channel)
    elif cmd == "set_outpoint":
        set_outpoint(tv_channel)
    elif cmd == "clear_outpoint":
        clear_outpoint(tv_channel)

    elif cmd == "toggle_show_tv_gui":
        toggle_show_tv_gui()
    elif cmd == "toggle_white_noise_on_channel_change":
        toggle_white_noise_on_channel_change()

    elif cmd == "zoom":
        if float(value) == 0:
            zoom(0, True)
        else:
            zoom(float(value))

    elif cmd == "shutdown":
        toggle_fill_color("black")
        time.sleep(1)  # Wait for user interface to load shutdown.html
        shutdown()
    elif cmd == "restart":
        restart_program_scheduled = True
    elif cmd == "reboot":
        time.sleep(1)  # Wait for user interface to load reboot.html
        reboot()
    elif cmd == "update":
        subprocess.Popen(["python3", f"{script_dir}/usb_update_checker.py"])
        sys.exit(0)
    elif cmd == "close_program":
        quit_program_scheduled = True

    elif cmd == "go_to_channel":
        go_to_channel(int(value))

    else:
        print("[tvPlayer] Unknown command:", cmd)

    # Save after 1s of no inputs
    debounce_save_settings()

def load_settings():
    """
    Load settings from a JSON file and apply them to globals.
    For file-dependent settings, only load settings for the files in the given filelist.
    """
    global pan_offsets, brightness, contrast, saturation, volume, show_tv_gui, zoom_level
    global file_settings, inpoints, video_fittings, video_speeds, tv_channel, show_whitenoise_channel_change
    global fill_color_type, fill_color_index, fill_color_active

    if not os.path.exists(os.path.join(script_dir, SETTINGS_FILE)):
        print(f"Settings file {SETTINGS_FILE} not found. Using defaults.")
        return
    
    # Handles:Empty file, Malformed JSON
    settings_path = os.path.join(script_dir, SETTINGS_FILE)
    with settings_lock:  # wait for the settings file to be accessible if needed
        try:
            with open(settings_path, "r") as f:
                content = f.read().strip()
                if not content:
                    raise ValueError("Empty file")
                data = json.loads(content)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[WARN] Failed to load settings: {e}. Using fallback.")
            data = {"general_settings": {}, "file_dependent_settings": {}}

    # Load general settings
    general_settings = data.get("general_settings", {})
    pan_offsets = general_settings.get("pan_offsets", pan_offsets)
    brightness = general_settings.get("brightness", brightness)
    contrast = general_settings.get("contrast", contrast)
    saturation = general_settings.get("saturation", saturation)
    volume = general_settings.get("volume", volume)
    fill_color_type = general_settings.get("fill_color_type", fill_color_type)
    fill_color_index = general_settings.get("fill_color_index", fill_color_index)
    fill_color_active = general_settings.get("fill_color_active", fill_color_active)
    tv_channel = general_settings.get("tv_channel", tv_channel)
    show_tv_gui = general_settings.get("show_tv_gui", show_tv_gui)
    show_whitenoise_channel_change = general_settings.get("show_whitenoise_channel_change", show_whitenoise_channel_change)
    zoom_level = general_settings.get("zoom_level", zoom_level)

    # Load filelist-dependent settings
    file_settings = data.get("file_dependent_settings", {})
    inpoints.clear()
    outpoints.clear()
    video_fittings.clear()
    video_speeds.clear()

    for filename in filelist:
        base_filename = os.path.basename(filename)
        settings = file_settings.get(base_filename, {})
        inpoints.append(settings.get("inpoints", 0))
        outpoints.append(settings.get("outpoints", 0))
        video_fittings.append(settings.get("video_fittings", 0))
        video_speeds.append(settings.get("video_speeds", 1.0))

    print("Settings loaded.")
    mqtt_handler.send("settings", "Settings loaded", {"settings": data, "filelist": filelist})

def debounce_save_settings():
    # Save after 1s of no inputs
    global _save_timer
    if _save_timer:
        _save_timer.cancel()
    _save_timer = threading.Timer(1.0, save_settings)
    _save_timer.start()

def save_settings():
    """
    Save the current settings to a JSON file, preserving settings for files not currently in the filelist.
    """
    data = collect_settings()

    # Save updated settings back to the file
    with open(os.path.join(script_dir, SETTINGS_FILE), "w") as f:
        json.dump(data, f, indent=4)

    print(f"Current state & settings saved to {SETTINGS_FILE}.")
    send_settings(data)

def send_settings(data=False):
    global last_sent_settings
    if not data:
        data = collect_settings()

    state = {
        "isPlaying": get_mpv_property("pause") == False, 
        "fillColorActive": fill_color_active,  # already in general_settings?
        "fillColorType": fill_color_type,  # already in general_settings?
        "fillColorIndex": fill_color_index[fill_color_type],  # already in general_settings?
        "currentFileName": current_file,
        "currentFileSettings": data["file_dependent_settings"].get(current_file, {}),
        "tvChannel": tv_channel, 
        "position": get_current_video_position(),
        "duration": get_mpv_property("duration")
    }

    mqtt_handler.send("settings", "Settings & current state", {"settings": data, "filelist": filelist, "state": state})
    last_sent_settings = time.time()


def collect_settings():
    global filelist, file_settings

    # Load existing settings from file, if any
    # Handles: Empty file, Malformed JSON
    settings_path = os.path.join(script_dir, SETTINGS_FILE)
    with settings_lock:  # wait for the settings file to be accessible if needed
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r") as f:
                    content = f.read().strip()
                    if not content:
                        raise ValueError("Empty file")
                    data = json.loads(content)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[WARN] Failed to load settings: {e}. Using fallback.")
                data = {"general_settings": {}, "file_dependent_settings": {}}
        else:
            data = {"general_settings": {}, "file_dependent_settings": {}}

    # Update general settings
    data["general_settings"].update({
        "pan_offsets": pan_offsets,
        "brightness": brightness,
        "contrast": contrast,
        "saturation": saturation,
        "volume": volume,
        "tv_channel": tv_channel,
        "fill_color_type": fill_color_type,
        "fill_color_index": fill_color_index,
        "fill_color_active": fill_color_active,
        "show_tv_gui": show_tv_gui,
        "show_whitenoise_channel_change": show_whitenoise_channel_change,
        "zoom_level": zoom_level,
    })

    # Add new files or update old ones to file_dependent_settings
    for i, file in enumerate(filelist):
        filename = os.path.basename(file)
        # FIXME
        # sometimes this fails because one USB was not ejected properly and "video_fittings[i]: index out of range" happens
        data["file_dependent_settings"][filename] = {
            "inpoints": inpoints[i] if i < len(inpoints) else 0,
            "outpoints": outpoints[i] if i < len(outpoints) else 0,
            "video_fittings": video_fittings[i] if i < len(video_fittings) else 0,
            "video_speeds": video_speeds[i] if i < len(video_speeds) else 0,
        }

    data["filelist_ignored"] = filelist_ignored

    return data

def server_init():
    # Wireless access point controlled self-sufficiently with RaspAP
    # Control the AP in the admin panel on a device that is connected to this raspis SSID "tvPlayer" here: http://10.3.141.1
    # Start serving ./webremote to http://10.3.141.1:8080
    server_script = os.path.join(script_dir, "server.py")
    subprocess.Popen(["python3", server_script])

def gpio_init():
    # GPIO Setup
    GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering
    GPIO.setup(LED_PIN, GPIO.OUT)  # LED as output
    GPIO.setup(BUTTON_PINS, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Buttons as input with pull-up resistors

    # Turn LED ON when script starts
    GPIO.output(LED_PIN, GPIO.HIGH)

    print("GPIO Initialized: LED ON, Buttons Ready")

def player_init():
    global player
    print("Starting mpv player via python-mpv (vo=drm, no UI).")

    player = mpv.MPV(
        vo='drm',
        loop_file='inf',
        idle=True,
        # Disable all mpv UI elements
        osc=False,
        osd_level=0,
        osd_bar=False,
        input_default_bindings=False,
        input_vo_keyboard=False,
        # Quiet
        terminal=False,
        msg_level='all=no',
    )

    print("mpv player initialized.")


def evdev_init():
    """
    Initialize evdev keyboard listener thread.
    Reads all /dev/input/event* devices that have EV_KEY capability.
    """
    global evdev_thread

    def evdev_listener():
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            print("[EVDEV] evdev not installed, keyboard input disabled.")
            return

        # Find all input devices with key capability
        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                if ecodes.EV_KEY in dev.capabilities():
                    devices.append(dev)
                    print(f"[EVDEV] Monitoring: {dev.name} ({dev.path})")
            except Exception:
                pass

        if not devices:
            print("[EVDEV] No keyboard devices found at startup, will keep scanning.")

        # Track modifier state
        shift_held = False
        ctrl_held = False
        SHIFT_KEYS = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
        CTRL_KEYS = {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL}
        known_paths = {dev.path for dev in devices}
        last_rescan = time.time()

        while True:
            # Rescan for hotplugged devices every 3 seconds
            now = time.time()
            if now - last_rescan >= 3:
                last_rescan = now
                for path in evdev.list_devices():
                    if path not in known_paths:
                        try:
                            dev = evdev.InputDevice(path)
                            if ecodes.EV_KEY in dev.capabilities():
                                devices.append(dev)
                                known_paths.add(path)
                                print(f"[EVDEV] Hotplugged: {dev.name} ({dev.path})")
                        except Exception:
                            pass

            if not devices:
                time.sleep(1)
                continue

            # Use select to wait for events from any device
            r, _, _ = select.select(devices, [], [], 1.0)
            for dev in r:
                try:
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY:
                            # Update modifier state
                            if event.code in SHIFT_KEYS:
                                shift_held = event.value != 0  # 1=press, 2=repeat, 0=release
                            elif event.code in CTRL_KEYS:
                                ctrl_held = event.value != 0
                            elif event.value == 1:  # key down (not repeat)
                                handle_evdev_key(event.code, shift=shift_held, ctrl=ctrl_held)
                except OSError:
                    # Device disconnected
                    known_paths.discard(dev.path)
                    devices.remove(dev)
                    print(f"[EVDEV] Disconnected: {dev.path}")

    evdev_thread = threading.Thread(target=evdev_listener, daemon=True)
    evdev_thread.start()


def handle_evdev_key(code, shift=False, ctrl=False):
    """
    Map evdev key codes to actions. Same mapping as the old pygame handler.
    """
    global quit_program_scheduled
    try:
        from evdev import ecodes
    except ImportError:
        return

    save_after_input = True

    if code == ecodes.KEY_UP and shift:
        pause()
        seek(0.04)
    elif code == ecodes.KEY_DOWN and shift:
        pause()
        seek(-0.04)
    elif code == ecodes.KEY_UP and ctrl:
        seek(60)
    elif code == ecodes.KEY_DOWN and ctrl:
        seek(-60)
    elif code == ecodes.KEY_UP:
        seek(5)
    elif code == ecodes.KEY_DOWN:
        seek(-5)
    elif code == ecodes.KEY_RIGHT:
        next_channel()
    elif code == ecodes.KEY_LEFT:
        prev_channel()
    elif code in (ecodes.KEY_SPACE, ecodes.KEY_P):
        toggle_play()
    elif code == ecodes.KEY_ESC:
        pass  # no fullscreen toggle in DRM mode
    elif code == ecodes.KEY_Q and shift:
        quit_program_scheduled = True
    elif code == ecodes.KEY_Q:
        shutdown()
    elif code == ecodes.KEY_B:
        toggle_fill_color("black")
    elif code == ecodes.KEY_X and ctrl:
        pan("reset", "x")
        pan("reset", "y")
    elif code == ecodes.KEY_X and shift:
        pan(-1, "x")
    elif code == ecodes.KEY_X:
        pan(1, "x")
    elif code == ecodes.KEY_Y and ctrl:
        pan("reset", "x")
        pan("reset", "y")
    elif code == ecodes.KEY_Y and shift:
        pan(-1, "y")
    elif code == ecodes.KEY_Y:
        pan(1, "y")
    elif code == ecodes.KEY_G and shift:
        select_fill_color(1, "green")
    elif code == ecodes.KEY_G and ctrl:
        select_fill_color(-1, "green")
    elif code == ecodes.KEY_G:
        toggle_fill_color("green")
    elif code == ecodes.KEY_C:
        set_video_fitting()
    elif code == ecodes.KEY_I and shift:
        clear_inpoint(tv_channel)
    elif code == ecodes.KEY_I:
        set_inpoint(tv_channel)
    elif code == ecodes.KEY_O and shift:
        clear_outpoint(tv_channel)
    elif code == ecodes.KEY_O:
        set_outpoint(tv_channel)
    elif code == ecodes.KEY_DOT and shift:
        zoom(0.01)
    elif code == ecodes.KEY_DOT and ctrl:
        zoom(0, True)
    elif code == ecodes.KEY_DOT:
        zoom(-0.01)
    elif code == ecodes.KEY_COMMA and shift:
        adjust_video_brightness(5)
    elif code == ecodes.KEY_COMMA:
        adjust_video_brightness(-5)
    elif code == ecodes.KEY_M and shift:
        adjust_video_contrast(5)
    elif code == ecodes.KEY_M:
        adjust_video_contrast(-5)
    elif code == ecodes.KEY_N and shift:
        adjust_video_saturation(5)
    elif code == ecodes.KEY_N:
        adjust_video_saturation(-5)
    elif code == ecodes.KEY_J:
        adjust_video_speed(-0.1)
    elif code == ecodes.KEY_K:
        adjust_video_speed("reset")
    elif code == ecodes.KEY_L:
        adjust_video_speed(0.1)
    elif code == ecodes.KEY_A:
        toggle_show_tv_gui()
    elif code == ecodes.KEY_W and shift:
        select_fill_color(1, "noise")
    elif code == ecodes.KEY_W:
        toggle_white_noise_on_channel_change()
    elif code == ecodes.KEY_MINUS or code == ecodes.KEY_KPMINUS:
        adjust_volume(-10)
    elif code == ecodes.KEY_EQUAL or code == ecodes.KEY_KPPLUS:
        adjust_volume(10)
    elif ecodes.KEY_1 <= code <= ecodes.KEY_9:
        go_to_channel(code - ecodes.KEY_1)
    elif code == ecodes.KEY_0:
        go_to_channel(9)
    elif ecodes.KEY_KP1 <= code <= ecodes.KEY_KP9:
        go_to_channel(code - ecodes.KEY_KP1)
    elif code == ecodes.KEY_KP0:
        go_to_channel(9)
    else:
        save_after_input = False

    if save_after_input:
        debounce_save_settings()

def system_init():
    global filelist, inpoints, window_width, window_height
    print("Get usb root")
    detect_usb_root()
    ensure_valid_settings()
    print("Get filelist")
    update_files_from_usb()
    show_no_signal()  # enable video for thumbnail creation images
    create_thumbnails(filelist)
    reset_in_outpoints_video_fitting()
    print(f"Initial filelist ({len(filelist)}):")
    print("  " + ("\n  ".join(f"Ch.{i+1} > {os.path.basename(file)}" for i, file in enumerate(filelist))))
    get_window_size()
    print(f"Screen size: {window_width} x {window_height}")

    load_settings()

    if fill_color_active:
        show_fill_color()
    elif len(filelist) > 0:
        print("Show first channel / first file or the one that was saved")
        go_to_channel(tv_channel)
    else:
        print("No USB plugged in during startup")
        show_no_signal()

    print("Wait for osd-dimensions")
    for _ in range(40):  # up to 10s
        osd_w = get_mpv_property("osd-dimensions/w")
        if osd_w is not None and osd_w > 0:
            break
        time.sleep(0.25)

    print("Wait for video width")
    for _ in range(40):  # up to 10s
        vid_w = get_mpv_property("width")
        if vid_w is not None and vid_w > 0:
            break
        time.sleep(0.25)

    # Set from load_settings()
    pan(pan_offsets["x"], "x")
    pan(pan_offsets["y"], "y")
    set_brightness(brightness)
    set_contrast(contrast)
    set_saturation(saturation)
    set_volume(volume)
    zoom(zoom_level, True)

    print("System initialized.\n")

def detect_usb_root():
    global usb_root
    # Automatically detect the user's home directory, find USB device
    username = pwd.getpwuid(os.getuid()).pw_name
    usb_root = os.path.join('/media', username)

    # Print the detected USB root for debugging purposes
    # print(f"USB root detected: {usb_root}")

def automount_usb():
    """Mount any unmounted USB partitions via udisksctl (headless has no file manager to do it)."""
    try:
        result = subprocess.run(
            ['lsblk', '-rno', 'NAME,TYPE,MOUNTPOINT'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            parts = line.split(' ')
            if len(parts) >= 2:
                name, dtype = parts[0], parts[1]
                mountpoint = parts[2] if len(parts) > 2 else ''
                # Mount unmounted USB partitions (sd* devices)
                if dtype == 'part' and name.startswith('sd') and not mountpoint:
                    dev_path = f'/dev/{name}'
                    print(f"[USB] Auto-mounting {dev_path}")
                    subprocess.run(
                        ['udisksctl', 'mount', '-b', dev_path, '--no-user-interaction'],
                        capture_output=True, timeout=10
                    )
    except Exception as e:
        print(f"[USB] automount error: {e}")

_last_usb_check = 0

def update_files_from_usb():
    global filelist, filelist_ignored, has_av_channel, _last_usb_check
    # Only check every 3 seconds — no point scanning files more often than drives appear
    now = time.time()
    if now - _last_usb_check < 3:
        return
    _last_usb_check = now

    # Mount any unmounted USB drives (headless has no automount)
    automount_usb()

    # Build into local lists so that a transient error on one device does not
    # wipe out files we already collected from other devices in the same scan.
    new_filelist = []
    new_filelist_ignored = []
    new_has_av_channel = False
    av_channel_path = ''

    if os.path.exists(usb_root):
        try:
            devices = os.listdir(usb_root)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Could not list usb_root {usb_root}: {e}. Keeping previous filelist.")
            return

        for device in devices:
            device_path = os.path.join(usb_root, device)
            if os.path.isdir(device_path):
                try:
                    for file in os.listdir(device_path):
                        if file.lower().endswith(allowed_fileendings) and not file.startswith('.'):
                            if file.lower().startswith("av."):
                                new_has_av_channel = True
                                av_channel_path = os.path.join(device_path, file)
                            else:
                                new_filelist.append(os.path.join(device_path, file))
                        elif not file.startswith('.'):
                            new_filelist_ignored.append(file)
                except PermissionError:
                    # Skip just this device; keep files already collected from others.
                    if device_path not in ignored_devices:
                        print(f"Permission denied while accessing: {device_path}. Ignoring this device.")
                        ignored_devices.append(device_path)
                    continue
                except FileNotFoundError:
                    print(f"Device {device_path} was removed. Ignoring this device.")
                    continue
                except Exception as e:
                    print(f"Another error occurred reading {device_path}: {e}. Ignoring this device.")
                    continue
        # Sort list naturally - 1.mp4, 2.mp4, 11.mp4 instead of 1.mp4, 11.mp4, 2.mp4
        new_filelist = natsorted(new_filelist, key=lambda x: x.lower())  # case insensitive

        if new_has_av_channel:
            new_filelist.append(av_channel_path)

        # Commit results atomically only after a full successful scan.
        filelist = new_filelist
        filelist_ignored = new_filelist_ignored
        has_av_channel = new_has_av_channel

def create_thumbnails(current_filelist):
    """
    Remove all images from ./webremote/thumbnails.
    For each file in current_filelist:
        - If it's an image, convert to 600px wide PNG if not already in ./webremote/thumbnails
        - If it's a video, extract a middle-frame PNG if not already in ./webremote/thumbnails
    """
    print("Create thumbnails from filelist..")
    if(len(current_filelist) > 0) :
        image_path = os.path.join(script_dir, 'assets', f'create_thumbnails.bgra')
        display_image(image_path, 3, 50,50, 1600,150, 4.0)

    mqtt_handler.send("general", "createThumbnails")

    thumbnail_folder = os.path.join(script_dir, "webremote", "thumbnails")
    os.makedirs(thumbnail_folder, exist_ok=True)

    # Step 1: remove existing thumbnails
    for f in os.listdir(thumbnail_folder):
        if f.endswith(".png"):
            os.remove(os.path.join(thumbnail_folder, f))

    # Step 2: generate new thumbnails
    for i, filepath in enumerate(current_filelist):
        if not filepath.lower().endswith(allowed_fileendings):
            continue

        if not os.path.exists(filepath):
            continue

        basename = os.path.splitext(os.path.basename(filepath))[0]
        thumb_path = os.path.join(thumbnail_folder, f"{basename}.png")

        if os.path.exists(thumb_path):
            continue

        image_path = os.path.join(script_dir, 'assets', 'channel_numbers', f'{i+1}.bgra')
        display_image(image_path, 4, max(int(window_width/2)-105, 50),max(int(window_height/2)-75, 200), 210,150, 666)

        if filepath.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.tiff', '.bmp')):
            # Generate thumbnail from image using ImageMagick
            subprocess.run([
                "convert", filepath,
                "-resize", "600x",
                thumb_path
            ])
        else:
            # Get video duration to find midpoint
            result = subprocess.run([
                "ffprobe", "-v", "error",
                "-hide_banner", "-loglevel", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath
            ], capture_output=True, text=True)

            try:
                duration = float(result.stdout.strip())
            except:
                duration = 1

            midpoint = duration / 2

            # Generate thumbnail from video using FFmpeg
            subprocess.run([
                "ffmpeg", "-y",
                "-hide_banner", "-loglevel", "error",
                "-ss", str(midpoint),
                "-i", filepath,
                "-vframes", "1",
                "-vf", "scale=600:-1",
                thumb_path
            ])

    print("Thumbnail creation complete.")

    image_path = os.path.join(script_dir, 'assets', 'channel_numbers', f'--.bgra')
    display_image(image_path, 4, max(int(window_width/2)-105, 50),max(int(window_height/2)-75, 200), 210,150, 0.1)



def reset_in_outpoints_video_fitting():
    global inpoints, outpoints, video_fittings, video_speeds
    inpoints = [0] * len(filelist)  # Create a list of zeros with the same length as filelist
    outpoints = [0] * len(filelist)  # Create a list of zeros with the same length as filelist
    video_fittings = [0] * len(filelist)  # Create a list of zeros with the same length as filelist
    video_speeds = [1.0] * len(filelist)  # Create a list of zeros with the same length as filelist

def get_window_size():
    global window_width, window_height
    # In DRM mode, get dimensions from mpv's osd-dimensions or fallback to defaults
    w = get_mpv_property("osd-dimensions/w")
    h = get_mpv_property("osd-dimensions/h")
    if w and h and w > 0 and h > 0:
        window_width, window_height = int(w), int(h)

def toggle_fill_color(type=False):
    global fill_color_type, fill_color_active

    # If its triggered by the same color and this is already showing, hide
    is_the_same = fill_color_type == type  
    # if called with no param, keep it the same for generalized uses
    fill_color_type = type if type else fill_color_type

    # Show or hide currently selected fill color (green/black or noise)
    if fill_color_active and is_the_same:
        print("is the same")
        # hide current fill color
        hide_fill_color()
    else:
        print("is NOT the same")
        show_fill_color()
        # show current fill color

def select_fill_color(step, type):
    global fill_color_type, fill_color_index
    fill_color_type = type

    # Cycle through all possible fill colors
    if fill_color_active:
        # show current + "step" fill color
        fill_color_index[fill_color_type] += step
        if fill_color_index[fill_color_type] < 0:
            fill_color_index[fill_color_type] = fill_color_max_index[fill_color_type]
        if fill_color_index[fill_color_type] > fill_color_max_index[fill_color_type]:
            fill_color_index[fill_color_type] = 0
    show_fill_color()

def show_fill_color():
    global fill_color_active
    fill_color_active = True  # MUST BE SET TO False WHENEVER I CHANNEL NEXT / PREV / PLAY THIS CHANNEL THING
    suffix = "mp4" if fill_color_type == 'noise' else "png"
    fill_color_path = os.path.join(script_dir, 'assets', 'fill_colors', f"{fill_color_type}{fill_color_index[fill_color_type]+1}.{suffix}")

    # Set fill colors always to stretch
    if player:
        player.speed = 1.0
        player.video_zoom = zoom_level
        player.keepaspect = False

    play_file(fill_color_path)

def hide_fill_color():
    global fill_color_active
    fill_color_active = False
    # Display previously played channel from inpoint if any file available
    if len(filelist) > 0:
        play_file(filelist[tv_channel], inpoints[tv_channel], outpoints[tv_channel])


def show_no_signal():
    # Show white noise in between channels or when no files on USB
    white_noise_path = os.path.join(script_dir, 'assets', 'fill_colors', f"noise{fill_color_index['noise']+1}.mp4")
    # Set white noise to always stretch
    if player:
        player.speed = 1.0
        player.video_zoom = zoom_level
        player.keepaspect = False
    play_file(white_noise_path)

def zoom(value, absolute=False):
    global zoom_level, window_width, window_height

    if absolute:
        zoom_level = value
    else:
        # Clamp zoom_level between -1.0 (very small) and 2.0 (very big)
        increment = value * (1 + abs(zoom_level))
        zoom_level = max(-3.0, min(3.0, zoom_level + increment))
    scale_factor = 2 ** zoom_level
    print(f"Set zoom to {zoom_level}, scale_factor: ", scale_factor)
    window_width = int(window_width * scale_factor)   # Scale window size for use of relative positioning with iamges etc
    window_height = int(window_height * scale_factor) # Scale window size for use of relative positioning with iamges etc
    if player:
        player.video_zoom = zoom_level

def set_brightness(value):
    if player:
        player.brightness = value
        print(f"Set brightness to {value}")

def adjust_video_brightness(value):
    global brightness
    # Clamp brightness between -100 (full transparent) and 100 (full bright)
    brightness = max(-100, min(100, brightness + value))
    set_brightness(brightness)

def set_contrast(value):
    if player:
        player.contrast = value
        print(f"Set contrast to {value}")

def adjust_video_contrast(value):
    global contrast
    # Clamp contrast between -100 (full dull) and 100 (max contrast)
    contrast = max(-100, min(100, contrast + value))
    set_contrast(contrast)

def set_saturation(value):
    if player:
        player.saturation = value
        print(f"Set saturation to {value}")

def adjust_video_saturation(value):
    global saturation
    # Clamp saturation between -100 (full greyscale) and 100 (max vibrance)
    saturation = max(-100, min(100, saturation + value))
    set_saturation(saturation)

def adjust_video_speed(value):
    global video_speeds
    # Clamp speed
    if value == 'reset':
        video_speeds[tv_channel] = 1.0
    else:
        # Apply exponential scaling for fine control at low speeds and larger steps at high speeds
        adjustment_factor = 2 ** value
        video_speeds[tv_channel] *= adjustment_factor
        # Clamp the speed between 0.05 and 3.0 (above 3.0 A/V desynchronization due to hardware limitations)
        video_speeds[tv_channel] = max(0.01, min(3.0, video_speeds[tv_channel]))

    set_playback_speed(video_speeds[tv_channel])

def set_playback_speed(value):
    if player:
        player.speed = value
        print(f"Set playback speed to {value}")

def pan(offset, axis):
    global pan_offsets

    # Update the pan offset for the specified axis
    if offset == "reset":
        pan_offsets[axis] = 0.0
    else:
        # video-pan-x = 0.0: No shift.
        # video-pan-x = 0.5: Shifts the video horizontally by half the displayed video width to the right.
        # video-pan-y = -0.25: Shifts the video vertically by one-quarter of the displayed video height upwards.
        pan_offsets[axis] += offset*0.0025

    # Set pixel value for image re-positionning
    if axis == "x":
        video_width = get_mpv_property("width")
        osd_dimensions_w = get_mpv_property("osd-dimensions/w")
        if not video_width or not osd_dimensions_w:
            print("problem getting width of video")
            return  # Ignore to not crash
        scaling_factor = osd_dimensions_w / video_width
        real_x = pan_offsets[axis] * video_width * scaling_factor
        pan_offsets[f"{axis}-real"] = int(real_x)
    else:
        video_height = get_mpv_property("height")
        osd_dimensions_h = get_mpv_property("osd-dimensions/h")
        if not video_height or not osd_dimensions_h:
            print("problem getting height of video")
            return  # Ignore to not crash
        scaling_factor = osd_dimensions_h / video_height
        real_y = pan_offsets[axis] * video_height * scaling_factor
        pan_offsets[f"{axis}-real"] = int(real_y)

    # Send the pan command to MPV
    if player:
        if axis == "x":
            player.video_pan_x = pan_offsets[axis]
        else:
            player.video_pan_y = pan_offsets[axis]
    print(f"Panned video {axis} to {pan_offsets[axis]:.3f}")

def set_volume(value):
    global muted
    muted = value == 0
    if player:
        player.volume = value
        print(f"Set volume to {value}")
        if show_tv_gui:
            image_path = os.path.join(script_dir, 'assets', 'volume_bars', f'volume_{value}.bgra')
            display_image(image_path, 2, int(window_width/2-800),window_height-225, 1600,150, 1.0)

def adjust_volume(value):
    global volume
    # Clamp volume between 0 and 100
    volume = max(0, min(100, volume + value))
    set_volume(volume)


def check_buttons():
    """
    Check GPIO buttons and trigger respective actions.
    """
    global tv_channel

    for i, pin in enumerate(BUTTON_PINS):
        if GPIO.input(pin) == GPIO.LOW:  # Button Pressed (active low)
            print(f"Button {i+1} Pressed!")
            time.sleep(0.05)  # Short debounce delay

            if i == 0:
                ## prev_channel()
                print("prev_channel()")
            elif i == 1:
                ## toggle_play()
                print("toggle_play()")
            elif i == 2:
                ## next_channel()
                print("next_channel()")
            elif i == 3:
                ## set_video_fitting()
                print("set_video_fitting()")
            elif i == 4:
                ## seek(-5)  # ?
                print("seek(-5)")
            elif i == 5:
                ## seek(5)  # ?
                print("seek(5)")
            elif i == 6:
                ## toggle_fill_color("black")
                print('toggle_fill_color("black")')
            elif i == 7:
                # set_inpoint(tv_channel)  # ?
                # select_fill_color(1, "green")
                print('select_fill_color(1, "green")')
            elif i == 8:
                # Extra physical btn
                shutdown()

            # Debounce until button is released
            while GPIO.input(pin) == GPIO.LOW:
                print(f"Wait for user to release button {i+1}..")
                time.sleep(0.05)

def prev_channel():
    global tv_channel
    # if current file as an in-point and current_time is bigger than that, skip to input and
    # pause() for resetting scene
    # FIXME: cannot skip to the beginning of the video if inpoint is set. need to clear inpoint first.
    # workaround: if is pausend and EXACTLY at the inpoint, jump() to beginning of video and play without
    # editing the inpoints (does that work or is ab-loop active?)
    if inpoints[tv_channel] > 0 and get_current_video_position() > inpoints[tv_channel]+2:
        go_to_channel(tv_channel)
        pause()
    else:
        tv_channel -= 1
        go_to_channel(tv_channel)

def next_channel():
    global tv_channel
    tv_channel += 1
    go_to_channel(tv_channel)

def go_to_channel(number):
    global tv_channel

    # If channel changes with arrow up/down when no actual files; ignore
    if(len(filelist) == 0):
        return

    # Wrap around channel
    number %= len(filelist)
    tv_channel = number

    if show_tv_gui:
        channel_to_display = tv_channel + tv_channel_offset
        if has_av_channel and tv_channel == len(filelist)-1:
            channel_to_display = "av"
        image_path = os.path.join(script_dir, 'assets', 'channel_numbers', f'{channel_to_display}.bgra')
        display_image(image_path, 1, window_width-315,50, 210,150, gui_display_duration)

    if show_whitenoise_channel_change:
        print("show_no_signal in between")
        show_no_signal()
        time.sleep(white_noise_duration)

    set_video_fitting(video_fittings[tv_channel])  # Set fit for this channel
    set_playback_speed(video_speeds[tv_channel])   # Set speed for this channel
    play_file(filelist[number], inpoints[number], outpoints[number])

def play_file(file, inpoint=0.0, outpoint=0.0):
    global current_file, fill_color_active
    if "assets/fill_colors" not in file:
        fill_color_active = False

    if player:
        print(f"Swapping to new file: {os.path.basename(file)} at {inpoint} seconds.")
        # Set start position before loading (mpv applies 'start' to the next loaded file)
        player['start'] = str(inpoint) if inpoint > 0 else '0'
        player.command('loadfile', file, 'replace')

        # ab-loop properties persist across loadfile in mpv, so we must always
        # set or clear them, otherwise a previous channel's outpoint can cause
        # the new file to loop back after only 1-2 frames.
        if outpoint > 0:
            activate_ab_loop(inpoint, outpoint)
        else:
            clear_ab_loop()

        # Ensure playback is resumed unconditionally after swapping files.
        # Relying on a pause-state check can fail if mpv has not yet updated
        # the property after loadfile, leading to a frozen first frame.
        player.pause = False

    current_file = os.path.basename(file)  # file

def play():
    if player:
        is_paused = player.pause
        if is_paused:
            player.pause = False
            print("Video playing.")

def pause():
    if player:
        player.pause = True
        print("Video paused.")

def activate_ab_loop(inpoint, outpoint):
    print("activate loop from ", inpoint, " to ", outpoint)
    if player:
        player.ab_loop_a = inpoint
        player.ab_loop_b = outpoint

def clear_ab_loop():
    # In mpv, "no" disables ab-loop endpoints. Must be sent for both a and b,
    # otherwise a previously set outpoint keeps looping the new file.
    if player:
        player.ab_loop_a = 'no'
        player.ab_loop_b = 'no'

def toggle_play():
    if player:
        player.cycle('pause')

def toggle_fullscreen():
    pass  # In DRM mode, always fullscreen — no-op

def seek(seconds):
    if player:
        if seconds < .2 and seconds > 0:
            # seek frame by frame forwards
            player.frame_step()
        elif seconds < 0 and seconds > -.2:
            # seek frame by frame backwards
            player.frame_back_step()
        else:
            player.seek(seconds, reference='relative')
        print(f"Seeking {seconds} seconds")

def jump(seconds):
    if player:
        player.seek(seconds, reference='absolute')

def set_inpoint(channel):
    global inpoints
    current_inpoint = get_current_video_position()
    inpoints[channel] = current_inpoint
    print(f"Set new inpoint for channel {channel}: {inpoints[channel]}")
    # Set A to now and B to whatever it is or end of file
    activate_ab_loop(inpoints[channel], get_mpv_property("duration") if outpoints[channel] == 0 else outpoints[channel])

def clear_inpoint(channel):
    global inpoints
    inpoints[channel] = 0
    print(f"Cleared inpoint for channel {channel}")
    # Set A to beginning and B to whatever it is or end of file
    activate_ab_loop(0, get_mpv_property("duration") if outpoints[channel] == 0 else outpoints[channel])

def set_outpoint(channel):
    global outpoints
    current_inpoint = get_current_video_position()
    outpoints[channel] = current_inpoint
    print(f"Set new outpoint for channel {channel}: {outpoints[channel]}")
    # Set A to whatever and B to now
    activate_ab_loop(inpoints[channel], outpoints[channel])
    # Go to start of loop
    jump(inpoints[channel])

def clear_outpoint(channel):
    global outpoints
    outpoints[channel] = 0
    print(f"Cleared outpoint for channel {channel}")
    # Set A to whatever and B to end of file
    activate_ab_loop(inpoints[channel], get_mpv_property("duration"))

def get_mpv_property(property_name):
    # run "mpv --list-properties" on raspi to see list of properties
    if not player:
        return None
    try:
        # For properties with slashes (e.g. "osd-dimensions/w"), use command interface
        if '/' in property_name:
            return player.command('get_property', property_name)
        # For normal properties, use python-mpv attribute access (returns proper Python types)
        attr_name = property_name.replace('-', '_')
        return getattr(player, attr_name)
    except Exception:
        return None

def get_current_video_position():
    time_pos = get_mpv_property("time-pos")
    if time_pos is not None:
        return time_pos
    return 0

def toggle_show_tv_gui():
    global show_tv_gui
    show_tv_gui = not show_tv_gui
    print(f"TV animations are {show_tv_gui}")
    
def toggle_white_noise_on_channel_change():
    global show_whitenoise_channel_change
    show_whitenoise_channel_change = not show_whitenoise_channel_change
    print(f"White noise between channel change is {show_whitenoise_channel_change}")

# List of fitting modes
def set_video_fitting(fitting_index=None):
    global tv_channel, window_height

    if fitting_index is None:  # If no fitting_index is specified, cycle through the modes
        print((video_fittings[tv_channel] + 1) % len(fitting_modes))
        video_fittings[tv_channel] = (video_fittings[tv_channel] + 1) % len(fitting_modes)
        new_mode = fitting_modes[video_fittings[tv_channel]]
    else:  # Set mode explicitly
        video_fittings[tv_channel] = fitting_index
        new_mode = fitting_modes[fitting_index]

    if player:
        if new_mode == 'contain':
            player.keepaspect = True
            player.panscan = 0.0
        elif new_mode == 'stretch':
            player.keepaspect = False
            player.panscan = 0.0
        elif new_mode == 'cover':
            player.keepaspect = True
            player.panscan = 1.0
        print(f"Video fitting set to: {new_mode}")


def display_image(image_path, overlay_id, x, y, width, height, display_duration=2.0):
    global active_overlays
    # image_path = os.path.join(script_dir, 'assets', 'channel_numbers', f'{number}.bgra')

    # Ensure the file exists
    if not os.path.exists(image_path):
        print(f"Image file not found: {image_path}")
        return

    if not player:
        return

    # Correction for panned video
    x += pan_offsets["x-real"]
    y += pan_offsets["y-real"]

    # Correct for zoomed video
    # Calculate original and scaled centers
    if zoom_level != 0.0:
        # ...zoom_level from -3.0 to +3.0
        scale_factor = 2 ** zoom_level  # Zoom by mpv is logarithmic
        center_x = window_width / 2
        center_y = window_height / 2
        scaled_center_x = center_x * scale_factor
        scaled_center_y = center_y * scale_factor
        # Calculate offsets to recenter
        offset_x = scaled_center_x - center_x
        offset_y = scaled_center_y - center_y
        # Apply zoom and recenter
        x = int((x * scale_factor) - offset_x)
        y = int((y * scale_factor) - offset_y)

    # Overlay-add command via python-mpv
    stride = width * 4  # BGRA has 4 bytes per pixel
    player.command("overlay-add", overlay_id, x, y, image_path, 0, "bgra", width, height, stride)

    # Cancel any existing overlay removal thread for this overlay_id
    if overlay_id in active_overlays:
        active_overlays[overlay_id].cancel()

    # Function to remove overlay after the duration
    def remove_overlay():
        try:
            player.command("overlay-remove", overlay_id)
            print(f"Removed overlay ID {overlay_id}")
        except Exception:
            pass

    # Start a new thread to remove the overlay and store it
    thread = threading.Timer(display_duration, remove_overlay)
    thread.start()
    active_overlays[overlay_id] = thread

    print(f"Displaying image: {os.path.basename(image_path)} (@ID:{overlay_id}) at x={x} y={y} for {display_duration} seconds")


def update_in_outpoints():
    global inpoints, outpoints
    inpoints = [0] * len(filelist)
    outpoints = [0] * len(filelist)

def close_program():
    global player
    print("Close the program..")
    GPIO.output(LED_PIN, GPIO.LOW)  # Turn LED OFF before exit
    GPIO.cleanup()  # Reset GPIO pins

    # needs to kill server.py aswell? however, that script kills older versions of itself

    # Terminate mpv player
    if player:
        try:
            player.terminate()
        except Exception as e:
            print("Failed to terminate mpv:", e)
        player = None

    print("..goodbye!")
    sys.exit()     # Exits the Python program

def shutdown():
    try:
        # Attempt to shut down the Raspberry Pi
        print("Attempting to shut down the Raspberry Pi...")
        result = os.system("sudo shutdown now")
        
        # Check if the command failed (non-zero return code indicates failure)
        if result != 0:
            raise PermissionError("Shutdown failed. Ensure the script is run with sudo privileges.")
    
    except PermissionError as e:
        print(f"Error: {e}")

def reboot():
    try:
        # Attempt to shut down the Raspberry Pi
        print("Attempting to reboot...")
        result = os.system("sudo reboot now")
        
        # Check if the command failed (non-zero return code indicates failure)
        if result != 0:
            raise PermissionError("Reboot failed. Ensure the script is run with sudo privileges.")
    
    except PermissionError as e:
        print(f"Error: {e}")

def ensure_valid_settings():
    path = os.path.join(script_dir, SETTINGS_FILE)
    default = {"general_settings": {}, "file_dependent_settings": {}}
    try:
        with open(path, "r") as f:
            json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("Settings file was empty - write default")
        with open(path, "w") as f:
            json.dump(default, f, indent=2)

def main():
    global last_sent_settings, fill_color_type
    time.sleep(2)  #
    print("--------------------------------------------------------------------------------")
    player_init()
    system_init()
    server_init()
    mqtt_init()
    udp_init()
    gpio_init()
    evdev_init()

    while True:
        now = time.time()
        get_window_size()
        check_buttons()
        if now - last_sent_settings >= 1:
            send_settings()
            last_sent_settings = now

        # Update file list if USB is inserted or removed
        old_filelist = filelist.copy()
        update_files_from_usb()

        #print("compare filelist")
        if filelist != old_filelist:
            # USB drive was taken out or inserted again
            update_in_outpoints()
            print(f"filelist updated ({len(filelist)}):")
            print("  " + ("\n  ".join(f"Ch.{i+1} > {os.path.basename(file)}" for i, file in enumerate(filelist))))
            create_thumbnails(filelist)
            print("inpoints and video fitting reset:")
            reset_in_outpoints_video_fitting()
            load_settings()  # why tho?
            # start first video
            go_to_channel(0)

        # If no files found, show white noise or blank screen
        if not filelist:
            if show_tv_gui:
                print("No files - show white noise - wait for USB")
                if not fill_color_active:
                    print("trigger show_no_signal()")
                    show_no_signal()
            else:
                print("No files available - show blank screen")
                if not fill_color_active:
                    fill_color_type = "black"
                    show_fill_color()  # FIXME: only once!

        if quit_program_scheduled:
            print("triggered quit_program_scheduled !!!")
            close_program()

        if restart_program_scheduled:
            restart_program("Restarting as demanded by user")

        time.sleep(0.1)

def save_crash_log(e, traceback_text):
    # Generate filename like logs/25-06-13_20.33_crashlog.log
    timestamp = time.strftime("%y-%m-%d_%H.%M")
    log_dir = os.path.join(script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, f"{timestamp}_crashlog.log")

    # Write to the crash log file
    with open(log_filename, "w") as f:
        f.write(f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Error: {str(e)}\n")
        f.write("------------\n\n")
        f.write(traceback_text)
        f.write("\n\n------------")

    print(f"[LOG] Crash log saved to {log_filename}")

def restart_program(msg="Restarting program due to critical error..."):
    # close_program()  # memory leaks if not close_program() but oh well
    print(msg)
    python = sys.executable
    os.execl(python, python, *sys.argv)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("\nProgram interrupted by user or crashed.")
        print("Main program error:", e)
        error_log = traceback.format_exc()
        print(error_log)
        save_crash_log(e, error_log)

        try:
            print("[DEBUG] Attempting to send MQTT error message...")
            mqtt_handler.send("general", "error", {
                "error": str(e),
                "traceback": error_log
            })
            time.sleep(0.5)  # give it time to send
        except Exception as send_err:
            print("[ERROR] Failed to send MQTT error message:", send_err)

        try:
            print("[DEBUG] Attempting to restart program...")
            restart_program()
        except Exception as restart_err:
            print("[ERROR] Failed to restart program:", restart_err)
