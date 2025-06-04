import os
import sys
import pygame  # pygame 1.9.6
import subprocess
import threading
import json
import time
from natsort import natsorted
import random
import RPi.GPIO as GPIO
import mqtt_handler

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
window_width = 0
window_height = 0
tv_channel = 0
filelist = []
inpoints = []
outpoints = []
video_fittings = []
video_speeds = []
ignored_devices = []
mpv_process = None  # Global variable to track the running mpv process
fitting_modes = ['contain', 'stretch', 'cover']  # List of fitting modes
is_black_screen = False
white_noise_files = ["white_noise_1.mp4","white_noise_2.mp4","white_noise_3.mp4","white_noise_4.mp4",]
white_noise_index = 0
current_file = ""
pan_offsets = {'x': 0.0, 'y': 0.0, 'x-real': 0, 'y-real': 0}  # Global variables to track the pan offsets
has_av_channel = False
ipc_socket_path = '/tmp/mpv_socket'
brightness = 0  # -100 to 100, default 0
contrast = 0  # -100 to 100, default 0
saturation = 0  # -100 to 100, default 0
volume = 100  # 0 to 100, 100 means max loudness
active_overlays = {}  # Dictionary to store active overlay threads
current_green_index = 0
last_mpv_state_sent = 0
zoom_level = 0.0

file_settings = {}
SETTINGS_FILE = "settings.json"

def mqtt_init():
    mqtt_handler.set_command_handler(mqtt_incoming)
    mqtt_handler.start()

def mqtt_incoming(data):
    # print("[tvPlayer] Command from MQTT:", data)

    cmd = data.get("command")
    value = data.get("value", 0)

    if cmd == "give_settings":
        # Triggers collection of settings including filelist and sends it to web by mqtt
        save_settings()
    elif cmd == "toggle_play":
        toggle_play()
    elif cmd == "toggle_fullscreen":
        toggle_fullscreen()

    elif cmd == "close_program":
        close_program()
    elif cmd == "jump":   # USE ME
        jump(float(value))
    elif cmd == "seek":  
        if value < 0.05 and value > -0.05:
            pause()
        seek(float(value))
    elif cmd == "next_channel":
        next_channel()
    elif cmd == "prev_channel":
        prev_channel()

    elif cmd == "adjust_volume":
        adjust_volume(int(value))

    elif cmd == "toggle_black_screen":
        toggle_black_screen()
    elif cmd == "set_video_fitting":
        set_video_fitting()

    elif cmd == "pan_reset":  # adjust in html
        pan("reset", "x")
        pan("reset", "y")
    elif cmd == "pan":
        pan(*value)

    elif cmd == "adjust_video_brightness":
        adjust_video_brightness(int(value))
    elif cmd == "adjust_video_contrast":
        adjust_video_contrast(int(value))
    elif cmd == "adjust_video_saturation":
        adjust_video_saturation(int(value))

    elif cmd == "adjust_video_speed":
        if value == "reset":
            adjust_video_speed(value)
        else:
            adjust_video_speed(float(value))

    elif cmd == "cycle_green_screen":
        cycle_green_screen(int(value))

    elif cmd == "toggle_white_noise_on_channel_change":
        toggle_white_noise_on_channel_change()
    elif cmd == "cycle_white_noise":
        cycle_white_noise()

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

    elif cmd == "zoom":
        if float(value) == 0:
            zoom(0, True)
        else:
            zoom(float(value))

    elif cmd == "shutdown":
        time.sleep(1)  # Wait for user interface to load shutdown.html
        shutdown()
    elif cmd == "reboot":
        time.sleep(1)  # Wait for user interface to load reboot.html
        reboot()

    elif cmd == "go_to_channel":
        go_to_channel(int(value))

    else:
        print("[tvPlayer] Unknown command:", cmd)

def load_settings():
    """
    Load settings from a JSON file and apply them to globals.
    For file-dependent settings, only load settings for the files in the given filelist.
    """
    global white_noise_index, pan_offsets, brightness, contrast, saturation, volume, current_green_index, show_tv_gui, zoom_level
    global file_settings, inpoints, video_fittings, video_speeds, tv_channel, show_whitenoise_channel_change

    if not os.path.exists(os.path.join(script_dir, SETTINGS_FILE)):
        print(f"Settings file {SETTINGS_FILE} not found. Using defaults.")
        return

    with open(os.path.join(script_dir, SETTINGS_FILE), "r") as f:
        data = json.load(f)

    # Load general settings
    general_settings = data.get("general_settings", {})
    white_noise_index = general_settings.get("white_noise_index", white_noise_index)
    pan_offsets = general_settings.get("pan_offsets", pan_offsets)
    brightness = general_settings.get("brightness", brightness)
    contrast = general_settings.get("contrast", contrast)
    saturation = general_settings.get("saturation", saturation)
    volume = general_settings.get("volume", volume)
    current_green_index = general_settings.get("current_green_index", current_green_index)
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


def save_settings():
    """
    Save the current settings to a JSON file, preserving settings for files not currently in the filelist.
    """
    global filelist, file_settings

    # Load existing settings from file, if any
    if os.path.exists(os.path.join(script_dir, SETTINGS_FILE)):
        with open(os.path.join(script_dir, SETTINGS_FILE), "r") as f:
            data = json.load(f)
    else:
        data = {"general_settings": {}, "file_dependent_settings": {}}

    # Update general settings
    data["general_settings"].update({
        "white_noise_index": white_noise_index,
        "pan_offsets": pan_offsets,
        "brightness": brightness,
        "contrast": contrast,
        "saturation": saturation,
        "volume": volume,
        "tv_channel": tv_channel,
        "current_green_index": current_green_index,
        "show_tv_gui": show_tv_gui,
        "show_whitenoise_channel_change": show_whitenoise_channel_change,
        "zoom_level": zoom_level,
    })

    # Add new files or update old ones to file_dependent_settings
    for i, file in enumerate(filelist):
        filename = os.path.basename(file)
        data["file_dependent_settings"][filename] = {
            "inpoints": inpoints[i],
            "outpoints": outpoints[i],
            "video_fittings": video_fittings[i],
            "video_speeds": video_speeds[i],
        }

    # Save updated settings back to the file
    with open(os.path.join(script_dir, SETTINGS_FILE), "w") as f:
        json.dump(data, f, indent=4)

    print(f"Settings saved to {SETTINGS_FILE}.")
    mqtt_handler.send("settings", "Settings saved", {"settings": data, "filelist": filelist})

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

def pygame_init():
    global screen, window_id, ipc_socket_path
    # Initialize pygame for keyboard input and fullscreen handling
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption('tvPlayer')
    pygame.mouse.set_visible(False)  # Hide the mouse cursor

    # Get the window ID to pass to mpv
    window_info = pygame.display.get_wm_info()
    window_id = window_info['window']  # Get the window ID for embedding mpv


def player_init():
    global mpv_process, window_id, ipc_socket_path
    print("Starting mpv process in idle mode for the first time.")
    
    # Command to start mpv in idle mode (no file needed, stays ready for commands)
    command = [
        'mpv', '--idle', '--loop-file', '--fs', '--quiet',
        '--no-input-terminal', '--input-ipc-server=' + ipc_socket_path, '--wid=' + str(window_id)
    ]
    # Execute the command and store the process
    mpv_process = subprocess.Popen(command)

    print("Wait for the socket to be created before proceeding..")
    time.sleep(3)

def system_init():
    global filelist, inpoints, window_width, window_height
    print("Get usb root")
    detect_usb_root()
    ensure_valid_settings()
    print("Get filelist")
    update_files_from_usb()
    create_thumbnails(filelist)
    reset_in_outpoints_video_fitting()
    print(f"Initial filelist ({len(filelist)}):")
    print("  " + ("\n  ".join(f"Ch.{i+1} > {os.path.basename(file)}" for i, file in enumerate(filelist))))
    get_window_size()
    print(f"Screen size: {window_width} x {window_height}")

    load_settings()

    if len(filelist) > 0:
        print("Show first channel / first file or the one that was saved")
        go_to_channel(tv_channel)
    else:
        print("No USB plugged in during startup")
        show_white_noise()

    print("Wait for osd-dimensions")
    while get_mpv_property("osd-dimensions/w") == None:
        time.sleep(0.25)

    print("Wait for video width")
    while get_mpv_property("width") == None:
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
    global usb_root, script_dir
    # Automatically detect the user's home directory, find USB device
    usb_root = os.path.join('/media', os.getlogin())

    # Print the detected USB root for debugging purposes
    # print(f"USB root detected: {usb_root}")

    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # print(f"script_dir detected: {script_dir}")

def update_files_from_usb():
    global filelist, video_fittings, video_speeds, has_av_channel, tv_channel_offset, tv_channel
    filelist = []  # Resets always
    av_channel_path = ''

    if os.path.exists(usb_root):
        for device in os.listdir(usb_root):
            device_path = os.path.join(usb_root, device)
            if os.path.isdir(device_path):
                try:
                    for file in os.listdir(device_path):
                        if file.lower().endswith(allowed_fileendings) and not file.startswith('.'):
                            if file.lower().startswith("av."):
                                has_av_channel = True
                                av_channel_path = os.path.join(device_path, file)
                            else:
                                filelist.append(os.path.join(device_path, file))
                except PermissionError:
                    # Skip this device if it's no longer accessible
                    if device_path not in ignored_devices:
                        print(f"Permission denied while accessing: {device_path}. Ignoring this device.")
                        ignored_devices.append(device_path)
                    filelist = []
                    video_fittings = []
                    video_speeds = []
                    has_av_channel = False
                    continue
                except FileNotFoundError:
                    print(f"Device {device_path} was removed. Ignoring this device.")
                    filelist = []
                    video_fittings = []
                    video_speeds = []
                    has_av_channel = False
                    continue
                except Exception as e:
                    print(f"Another error occurred: {e}. Ignoring this device.")
                    filelist = []
                    video_fittings = []
                    video_speeds = []
                    has_av_channel = False
                    continue
        # Sort list naturally - 1.mp4, 2.mp4, 11.mp4 instead of 1.mp4, 11.mp4, 2.mp4
        filelist = natsorted(filelist, key=lambda x: x.lower())  # case insensitive

        if has_av_channel:
            filelist.append(av_channel_path)
        else:
            has_av_channel = False  # This makes no sense but its needed to show white noise when no USB is inserted

def create_thumbnails(current_filelist):
    """
    Remove all images from ./webremote/thumbnails.
    For each file in current_filelist:
        - If it's an image, convert to 600px wide PNG if not already in ./webremote/thumbnails
        - If it's a video, extract a middle-frame PNG if not already in ./webremote/thumbnails
    """
    print("Create thumbnails from filelist..")
    mqtt_handler.send("general", "createThumbnails")

    thumbnail_folder = os.path.join(script_dir, "webremote", "thumbnails")
    os.makedirs(thumbnail_folder, exist_ok=True)

    # Step 1: remove existing thumbnails
    for f in os.listdir(thumbnail_folder):
        if f.endswith(".png"):
            os.remove(os.path.join(thumbnail_folder, f))

    # Step 2: generate new thumbnails
    for filepath in current_filelist:
        if not filepath.lower().endswith(allowed_fileendings):
            continue

        if not os.path.exists(filepath):
            continue

        basename = os.path.splitext(os.path.basename(filepath))[0]
        thumb_path = os.path.join(thumbnail_folder, f"{basename}.png")

        if os.path.exists(thumb_path):
            continue

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



def reset_in_outpoints_video_fitting():
    global inpoints, outpoints, video_fittings, video_speeds
    inpoints = [0] * len(filelist)  # Create a list of zeros with the same length as filelist
    outpoints = [0] * len(filelist)  # Create a list of zeros with the same length as filelist
    video_fittings = [0] * len(filelist)  # Create a list of zeros with the same length as filelist
    video_speeds = [1.0] * len(filelist)  # Create a list of zeros with the same length as filelist

def get_window_size():
    global screen, window_width, window_height
    window_size = screen.get_size()
    window_width, window_height = int(window_size[0]), int(window_size[1])

def show_white_noise():  # (duration)
    global current_file
    # Launch mpv to play the video if  not already playing
    white_noise_path = os.path.join(script_dir, 'assets', 'white_noise', white_noise_files[white_noise_index])
    if not current_file == white_noise_path:
        # Set white noise to always stretch
        speed_command = f'echo \'{{"command": ["set_property", "speed", "1.0"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        zoom_command = f'echo \'{{"command": ["set_property", "video-zoom", "{zoom_level}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        aspect_command = f'echo \'{{"command": ["set_property", "keepaspect", "no"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(speed_command, shell=True)
        subprocess.call(zoom_command, shell=True)
        subprocess.call(aspect_command, shell=True)
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
    zoom_command = f'echo \'{{"command": ["set_property", "video-zoom", "{zoom_level}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
    subprocess.call(zoom_command, shell=True)

def set_brightness(value):
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        command = f'echo \'{{"command": ["set_property", "brightness", {value}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Set brightness to {value}")
    else:
        print("mpv IPC socket not found.")

def adjust_video_brightness(value):
    global brightness
    # Clamp brightness between -100 (full transparent) and 100 (full bright)
    brightness = max(-100, min(100, brightness + value))
    set_brightness(brightness)

def set_contrast(value):
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        command = f'echo \'{{"command": ["set_property", "contrast", {value}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Set contrast to {value}")
    else:
        print("mpv IPC socket not found.")

def adjust_video_contrast(value):
    global contrast
    # Clamp contrast between -100 (full dull) and 100 (max contrast)
    contrast = max(-100, min(100, contrast + value))
    set_contrast(contrast)

def set_saturation(value):
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        command = f'echo \'{{"command": ["set_property", "saturation", {value}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Set saturation to {value}")
    else:
        print("mpv IPC socket not found.")

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
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        command = f'echo \'{{"command": ["set_property", "speed", {value}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Set playback speed to {value}")
    else:
        print("mpv IPC socket not found.")

def pan(offset, axis):
    global pan_offsets, ipc_socket_path

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
        if not video_width:
            print("problem getting width of video")
            return  # Ignore to not crash
        scaling_factor = get_mpv_property("osd-dimensions/w") / video_width
        real_x = pan_offsets[axis] * video_width * scaling_factor
        pan_offsets[f"{axis}-real"] = int(real_x)
    else:
        video_height = get_mpv_property("height")
        if not video_height:
            print("problem getting height of video")
            return  # Ignore to not crash
        scaling_factor = get_mpv_property("osd-dimensions/h") / video_height
        real_y = pan_offsets[axis] * video_height * scaling_factor
        pan_offsets[f"{axis}-real"] = int(real_y)

    # Send the pan command to MPV
    pan_property = f"video-pan-{axis}"
    command = f'echo \'{{"command": ["set_property", "{pan_property}", {pan_offsets[axis]}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
    subprocess.call(command, shell=True)
    print(f"Panned video {axis} to {pan_offsets[axis]:.3f}")

def set_volume(value):
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        command = f'echo \'{{"command": ["set_property", "volume", {value}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Set volume to {value}")
        if show_tv_gui:
            image_path = os.path.join(script_dir, 'assets', 'volume_bars', f'volume_{value}.bgra')
            display_image(image_path, 2, int(window_width/2-800),window_height-225, 1600,150, 1.0)
    else:
        print("mpv IPC socket not found.")

def adjust_volume(value):
    global volume
    # Clamp volume between 0 and 100
    volume = max(0, min(100, volume + value))
    set_volume(volume)

def toggle_black_screen():
    global is_black_screen
    if is_black_screen:
        # Restore normal brightness
        set_brightness(0)
        play()
        mqtt_handler.send("general", "fillcolor", {"type": "black", "show": False})
    else:
        # Set brightness to -100 to black out the screen
        set_brightness(-100)
        pause()
        mqtt_handler.send("general", "fillcolor", {"type": "black", "show": True})
    is_black_screen = not is_black_screen

def cycle_green_screen(direction):
    global current_green_index, current_file
    max_green_templates = 19
    # Only increase green index when already showing green
    # if coming from another channel show the green thats was selected lastly
    green_path = os.path.join(script_dir, 'assets', 'greenscreen', f'{current_green_index+1}.png')
    if current_file == green_path:
        if direction != 0:
            # Switch to next/prev green img
            current_green_index = (current_green_index + direction) % (max_green_templates + 1)
            green_path = os.path.join(script_dir, 'assets', 'greenscreen', f'{current_green_index+1}.png')
        else:
            # Play last video file from inpoint
            play_file(filelist[tv_channel], inpoints[tv_channel], outpoints[tv_channel])
            mqtt_handler.send("general", "fillcolor", {"type": "green", "index": current_green_index, "show": False})
            return
    # Show green screen
    play_file(green_path)
    mqtt_handler.send("general", "fillcolor", {"type": "green", "index": current_green_index, "show": True})

def check_keypresses():
    global tv_channel
    for event in pygame.event.get():
        save_after_input = True
        """ if event.type == pygame.ACTIVEEVENT:
            if event.gain == 0:  # Focus lost
                print("Focus lost. Should we attempt to regain focus...?")
                #pygame.display.set_mode((0, 0), pygame.FULLSCREEN)  # Regain focus """

        if event.type == pygame.QUIT:
            print("Window closed - trigger pygame to quit")
            pygame.quit()
            sys.exit()  # Exit the program when the window is closed
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[UP] seek +0.04s")
                pause()
                seek(.04)  # smaller than 0.2s: frame-by-frame
            elif event.key == pygame.K_DOWN and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[DOWN] seek -0.04s")
                pause()
                seek(-.04)  # smaller than 0.2s: frame-by-frame
            elif event.key == pygame.K_UP and pygame.key.get_mods() & pygame.KMOD_CTRL:
                print("keypress [CTRL]+[UP] seek +60")
                seek(60)
            elif event.key == pygame.K_DOWN and pygame.key.get_mods() & pygame.KMOD_CTRL:
                print("keypress [CTRL]+[DOWN] seek -60")
                seek(-60)
            elif event.key == pygame.K_UP:
                print("keypress [UP] seek +5s")
                seek(5)
            elif event.key == pygame.K_DOWN:
                print("keypress [DOWN] seek -5s")
                seek(-5)
            elif event.key == pygame.K_RIGHT:
                print("keypress [RIGHT] next channel")
                next_channel()
            elif event.key == pygame.K_LEFT:
                print("keypress [LEFT] prev channel")
                prev_channel()
            elif event.key == pygame.K_SPACE or event.key == pygame.K_p:
                print("keypress [p] toggle play")
                toggle_play()
            elif event.key == pygame.K_ESCAPE:
                print("keypress [ESC] toggle fullscreen")
                toggle_fullscreen()
            elif event.key == pygame.K_q and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[q] close program")
                close_program()
            elif event.key == pygame.K_q:
                print("keypress [q] shutdwon computer")
                shutdown()
            elif event.key == pygame.K_b:
                print("keypress [b] toggle black screen")
                toggle_black_screen()
            elif (event.key == pygame.K_x or event.key == pygame.K_y) and pygame.key.get_mods() & pygame.KMOD_CTRL:
                print("keypress [CTRL]+[x] or [CTRL]+[y] reset pan")
                pan("reset", "x")
                pan("reset", "y")
            elif event.key == pygame.K_x and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[x] pan left")
                pan(-1, "x")
            elif event.key == pygame.K_x:
                print("keypress [x] pan right")
                pan(1, "x")
            elif event.key == pygame.K_y and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[y] pan up")
                pan(-1, "y")
            elif event.key == pygame.K_y:
                print("keypress [y] pan down")
                pan(1, "y")
            elif event.key == pygame.K_g and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[g] Cycle green screen index+")
                cycle_green_screen(1)
            elif event.key == pygame.K_g and pygame.key.get_mods() & pygame.KMOD_CTRL:
                print("keypress [CTRL]+[g] Cycle green screen index-")
                cycle_green_screen(-1)
            elif event.key == pygame.K_g:
                print("keypress [g] Toggle green screen")
                cycle_green_screen(0)
            elif event.key == pygame.K_c:
                print("keypress [c] Set video fitting")
                set_video_fitting()
            elif event.key == pygame.K_i and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[i] Clear inpoints")
                clear_inpoint(tv_channel)
            elif event.key == pygame.K_i:
                print("keypress [i] set inpoint")
                set_inpoint(tv_channel)
            elif event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[o] Clear outpoints")
                clear_outpoint(tv_channel)
            elif event.key == pygame.K_o:
                print("keypress [o] set outpoint")
                set_outpoint(tv_channel)
            elif event.key == pygame.K_PERIOD and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[.] Zoom in")
                zoom(0.01)
            elif event.key == pygame.K_PERIOD and pygame.key.get_mods() & pygame.KMOD_CTRL:
                print("keypress [CTRL]+[.] Zoom reset")
                zoom(0, True)
            elif event.key == pygame.K_PERIOD:
                print("keypress [SHIFT]+[.] Zoom out")
                zoom(-0.01)
            elif event.key == pygame.K_COMMA and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[,] More brightness")
                adjust_video_brightness(5)
            elif event.key == pygame.K_COMMA:
                print("keypress [,] Less brightness")
                adjust_video_brightness(-5)
            elif event.key == pygame.K_m and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[m] More contrast")
                adjust_video_contrast(5)
            elif event.key == pygame.K_m:
                print("keypress [m] Less contrast")
                adjust_video_contrast(-5)
            elif event.key == pygame.K_n and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[n] More saturation")
                adjust_video_saturation(5)
            elif event.key == pygame.K_n:
                print("keypress [n] Less saturation")
                adjust_video_saturation(-5)
            elif event.key == pygame.K_j:
                print("keypress [j] Playback speed slower")
                adjust_video_speed(-.1)
            elif event.key == pygame.K_k:
                print("keypress [k] Playback speed reset")
                adjust_video_speed("reset")
            elif event.key == pygame.K_l:
                print("keypress [l] Playback speed faster")
                adjust_video_speed(+.1)
            elif event.key == pygame.K_a:
                print("keypress [a] toggle TV GUI")
                toggle_show_tv_gui()
            elif event.key == pygame.K_w and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT]+[w] cycle white noise index")
                cycle_white_noise()
            elif event.key == pygame.K_w:
                print("keypress [w] toggle white noise on channel change")
                toggle_white_noise_on_channel_change()
            elif event.key == pygame.K_MINUS or (event.key == pygame.K_SLASH and pygame.key.get_mods() & pygame.KMOD_SHIFT) or pygame.key.name(event.key) == "[-]":
                print("keypress [-] Less volume")
                adjust_volume(-10)
            elif event.key == pygame.K_PLUS or (event.key == pygame.K_1 and pygame.key.get_mods() & pygame.KMOD_SHIFT) or pygame.key.name(event.key) == "[+]":
                print("keypress [+] More volume")
                adjust_volume(10)
            elif pygame.K_0 <= event.key <= pygame.K_9:
                print(f"keypress [number] {pygame.key.name(event.key)} go to channel")
                go_to_channel(event.key - pygame.K_0 - 1)  # -1 because pressing 1 should play file on key 0 not file key nr 1
            elif pygame.K_KP0 <= event.key <= pygame.K_KP9:
                print(f"keypress [number@numpad] {event.key} go to channel")
                go_to_channel(event.key - pygame.K_KP0 - 1)  # -1 because pressing 1 should play file on key 0 not file key nr 1
            else:
                print("other key: "+ pygame.key.name(event.key))
                save_after_input = False

            # Save on any valid keypress
            if save_after_input:
                save_settings()

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
                ## toggle_black_screen()
                print("toggle_black_screen()")
            elif i == 7:
                # set_inpoint(tv_channel)  # ?
                ## cycle_green_screen(0)
                print("cycle_green_screen(0)")
            elif i == 8:
                # Extra physical btn
                shutdown()

            # Debounce until button is released
            while GPIO.input(pin) == GPIO.LOW:
                print(f"Wait for user to release button {i+1}..")
                time.sleep(0.05)

def send_mpv_state():
    # Ttrigger settings to have current data about the playing file on web
    save_settings()
    mqtt_handler.send("general", "state", {
        "isPlaying": not get_mpv_property("pause"), 
        "currentFile": current_file, 
        "tvChannel": tv_channel, 
        "position": get_current_video_position(),
        "duration": get_mpv_property("duration")
    })


def prev_channel():
    global tv_channel
    # if current file as an in-point and current_time is bigger than that, skip to input and
    # pause() for resetting scene
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
        print("show_white_noise in between")
        show_white_noise()
        time.sleep(white_noise_duration)

    set_video_fitting(video_fittings[tv_channel])  # Set fit for this channel
    set_playback_speed(video_speeds[tv_channel])   # Set speed for this channel
    play_file(filelist[number], inpoints[number], outpoints[number])

def play_file(file, inpoint=0.0, outpoint=0.0):
    global mpv_process, current_file, ipc_socket_path
    if os.path.exists(ipc_socket_path):
        print(f"Swapping to new file: {os.path.basename(file)} at {inpoint} seconds.")
        # Use loadfile command to replace the video source without stopping mpv
        command = f'echo \'{{"command": ["loadfile", "{file}", "replace", "start={inpoint}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        
        # This works even though it should not
        # Inpoint is set by "start={inpoint}" above, but why does it loop? 
        if outpoint > 0:
            activate_ab_loop(inpoint, outpoint)

    current_file = file
    play()  # if paused, resume anyways

def play():
    global ipc_socket_path
    is_paused = get_mpv_property("pause")
    if is_paused is not None and is_paused:
        command = 'echo \'{"command": ["set_property", "pause", false]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print("Video playing.")

def pause():
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        command = 'echo \'{"command": ["set_property", "pause", true]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print("Video paused.")
    else:
        print("mpv IPC socket not found.")

def activate_ab_loop(inpoint, outpoint):
    print("activate loop from ", inpoint, " to ", outpoint)
    command_aba = f'echo \'{{"command": ["set_property", "ab-loop-a", {inpoint}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
    subprocess.call(command_aba, shell=True)
    command_abb = f'echo \'{{"command": ["set_property", "ab-loop-b", {outpoint}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
    subprocess.call(command_abb, shell=True)

def toggle_play():
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        # Send the pause command to the running mpv instance via IPC
        command = 'echo \'{"command": ["cycle", "pause"]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
    else:
        print("mpv IPC socket not found.")

def toggle_fullscreen():
    pygame.display.toggle_fullscreen()

def seek(seconds):
    global ipc_socket_path
    if os.path.exists(ipc_socket_path):
        # Create the command to send a seek command to the running mpv instance via IPC
        if seconds < .2 and seconds > 0:
            # seek frame by frame forwards
            command = 'echo \'{"command": ["frame-step"]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        elif seconds < 0 and seconds > -.2:
            # seek frame by frame backwards
            command = 'echo \'{"command": ["frame-back-step"]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        else:
            command = f'echo \'{{"command": ["seek", {seconds}, "relative"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Seeking {seconds} seconds")
    else:
        print("mpv IPC socket not found.")

def jump(seconds):
    command = f'echo \'{{"command": ["seek", {seconds}, "absolute"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
    subprocess.call(command, shell=True)

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
    global ipc_socket_path
    # run "mpv --list-properties" on raspi to see list of properties
    if os.path.exists(ipc_socket_path):
        # Construct the command to get the property from mpv
        command = f'echo \'{{"command": ["get_property", "{property_name}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path}'
        try:
            result = subprocess.check_output(command, shell=True).decode('utf-8').strip()
            response = json.loads(result)
            return response.get("data", None)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            print(f"Failed to get property {property_name} from mpv.")
            return None
    else:
        print("mpv IPC socket not found.")
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

def cycle_white_noise():
    global white_noise_index, show_whitenoise_channel_change
    show_whitenoise_channel_change = True
    white_noise_index += 1
    if white_noise_index > len(white_noise_files)-1:
        white_noise_index = 0
    print("white_noise_index>", white_noise_index)
    show_white_noise()
    # FIXME needs to behave like greenscreen
    mqtt_handler.send("general", "fillcolor", {"type": "noise", "index": white_noise_index, "show": True})

# List of fitting modes
def set_video_fitting(fitting_index=None):
    global tv_channel, window_height, ipc_socket_path

    if fitting_index is None:  # If no fitting_index is specified, cycle through the modes
        print((video_fittings[tv_channel] + 1) % len(fitting_modes))
        video_fittings[tv_channel] = (video_fittings[tv_channel] + 1) % len(fitting_modes)
        new_mode = fitting_modes[video_fittings[tv_channel]]
    else:  # Set mode explicitly
        video_fittings[tv_channel] = fitting_index
        new_mode = fitting_modes[fitting_index]

    if os.path.exists(ipc_socket_path):
        if new_mode == 'contain':
            keepaspect = "yes"
            panscan = 0  # Default, no cropping (black bars remain to preserve aspect ratio).
        elif new_mode == 'stretch':
            keepaspect = "no"
            panscan = 0  # Default, no cropping (black bars remain to preserve aspect ratio).
        elif new_mode == 'cover':
            keepaspect = "yes"
            panscan = 1  # Crops enough to completely fill the screen (removes all black bars).
            
        panscan_command = f'echo \'{{"command": ["set_property", "panscan", "{panscan}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(panscan_command, shell=True)
        aspect_command = f'echo \'{{"command": ["set_property", "keepaspect", "{keepaspect}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(aspect_command, shell=True)
        print(f"Video fitting set to: {new_mode} with pan-scan {panscan}")
    else:
        print("mpv IPC socket not found.")


def display_image(image_path, overlay_id, x, y, width, height, display_duration=2.0):
    global active_overlays, ipc_socket_path
    # image_path = os.path.join(script_dir, 'assets', 'channel_numbers', f'{number}.bgra')

    # Ensure the file exists
    if not os.path.exists(image_path):
        print(f"Image file not found: {image_path}")
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

    # Overlay-add command
    stride = width * 4  # BGRA has 4 bytes per pixel
    command = f'echo \'{{"command": ["overlay-add", {overlay_id}, {x}, {y}, "{image_path}", 0, "bgra", {width}, {height}, {stride}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
    subprocess.call(command, shell=True)

    # Cancel any existing overlay removal thread for this overlay_id
    if overlay_id in active_overlays:
        active_overlays[overlay_id].cancel()

    # Function to remove overlay after the duration
    def remove_overlay():
        time.sleep(display_duration)
        remove_command = f'echo \'{{"command": ["overlay-remove", {overlay_id}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(remove_command, shell=True)
        print(f"Removed overlay ID {overlay_id}")
    
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
    print("Close the program..")
    # GPIO.output(LED_PIN, GPIO.LOW)  # Turn off LED - maybe not so it glows until pi is shut down properly?
    GPIO.output(LED_PIN, GPIO.LOW)  # Turn LED OFF before exit
    GPIO.cleanup()  # Reset GPIO pins
    print("..goodbye!")
    pygame.quit()  # Closes the Pygame window
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
    global last_mpv_state_sent
    print("--------------------------------------------------------------------------------")
    pygame_init()
    player_init()
    system_init()
    server_init()
    mqtt_init()
    gpio_init()

    while True:
        now = time.time()
        get_window_size()
        check_buttons()
        check_keypresses()
        if now - last_mpv_state_sent >= 1:
            send_mpv_state()
            last_mpv_state_sent = now

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
            load_settings()
            # start first video
            go_to_channel(0)

        # If no files found, show white noise or blank screen
        if not filelist:
            if show_tv_gui:
                print("No files - show white noise - wait for USB")
                show_white_noise()
            else:
                print("No files available - show blank screen")

        pygame.display.update()
        time.sleep(0.1)

def restart_program():
    print("Restarting program due to critical error...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # If crash: Run the script again because I learnt nothing
        print("\nProgram interrupted by user or crashed.")
        print("Error: ", e)
        # restart_program()  ## TODO FINALLY !!
    finally:
        close_program()
