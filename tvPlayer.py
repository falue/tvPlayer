import os
import sys
import pygame
import subprocess
import threading
import json
from time import sleep
from natsort import natsorted
import random

# Customizing
show_tv_gui = True  # show number of channels top right and volume bar
show_whitenoise_channel_change = True  # white noise in between channel switching
white_noise_duration = 0.1  # duration which shows white noise when changing channels, in seconds
gui_display_duration = 2.0  # Duration of the gui numbers stays alive, minus the white_noise_duration, in seconds
tv_channel_offset = 1  # display higher channel nr than actually available

# Leave me be
window_width = 0
window_height = 0
tv_channel = 0
filelist = []
inpoints = []
video_fittings = []
mpv_process = None  # Global variable to track the running mpv process
fitting_modes = ['contain', 'stretch', 'cover']  # List of fitting modes
is_black_screen = False
white_noise_files = ["white_noise_1.mp4","white_noise_2.mp4","white_noise_3.mp4","white_noise_4.mp4",]
white_noise_index = 0
current_file = ""
has_av_channel = False
ipc_socket_path = '/tmp/mpv_socket'
brightness = 0  # 0 means 100% brightness
volume = 100  # 100 means max loudness
active_overlays = {}  # Dictionary to store active overlay threads
current_green_index = 0

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
    sleep(3)

def system_init():
    global filelist, inpoints, window_width, window_height
    print("Get usb root")
    detect_usb_root()
    print("Get filelist")
    update_files_from_usb()
    reset_inpoints_video_fitting()
    print(f"Initial filelist ({len(filelist)}):")
    print("  " + ("\n  ".join(f"Ch.{i+1} > {os.path.basename(file)}" for i, file in enumerate(filelist))))
    get_window_size()
    print(f"Screen size: {window_width} x {window_height}")

    print("Show first channel / first file")
    go_to_channel(0)

def detect_usb_root():
    global usb_root, script_dir
    # Automatically detect the user's home directory, find USB device
    usb_root = os.path.join('/media', os.getlogin())

    # Print the detected USB root for debugging purposes
    print(f"USB root detected: {usb_root}")

    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"script_dir detected: {script_dir}")

def update_files_from_usb():
    global filelist, video_fittings, has_av_channel, tv_channel_offset, tv_channel
    filelist = []  # Resets always
    av_channel_path = ''

    if os.path.exists(usb_root):
        for device in os.listdir(usb_root):
            device_path = os.path.join(usb_root, device)
            if os.path.isdir(device_path):
                try:
                    for file in os.listdir(device_path):
                        allowed_fileendings = (
                            '.mp4', '.mkv', '.avi', '.mxf', '.mov',
                            '.jpg', '.jpeg', '.png', '.gif', '.tiff', '.bmp'
                        )
                        if file.lower().endswith(allowed_fileendings) and not file.startswith('.'):
                            if file.lower().startswith("av."):
                                has_av_channel = True
                                av_channel_path = os.path.join(device_path, file)
                            else:
                                filelist.append(os.path.join(device_path, file))
                except PermissionError:
                    # Skip this device if it's no longer accessible
                    print(f"Permission denied while accessing: {device_path}. Ignoring this device.")
                    filelist = []
                    video_fittings = []
                    has_av_channel = False
                    continue
                except FileNotFoundError:
                    print(f"Device {device_path} was removed. Ignoring this device.")
                    filelist = []
                    video_fittings = []
                    has_av_channel = False
                    continue
                except Exception as e:
                    print(f"Another error occurred: {e}. Ignoring this device.")
                    filelist = []
                    video_fittings = []
                    has_av_channel = False
                    continue
        # Sort list naturally - 1.mp4, 2.mp4, 11.mp4 instead of 1.mp4, 11.mp4, 2.mp4
        filelist = natsorted(filelist, key=lambda x: x.lower())  # case insensitive

        if has_av_channel:
            filelist.append(av_channel_path)
        else:
            has_av_channel = False  # This makes no sense but its needed to show white noise when no USB is inserted

def reset_inpoints_video_fitting():
    global inpoints, video_fittings
    inpoints = [0] * len(filelist)  # Create a list of zeros with the same length as filelist
    video_fittings = [0] * len(filelist)  # Create a list of zeros with the same length as filelist

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
        zoom_command = f'echo \'{{"command": ["set_property", "video-zoom", "0"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        aspect_command = f'echo \'{{"command": ["set_property", "keepaspect", "no"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(zoom_command, shell=True)
        subprocess.call(aspect_command, shell=True)
        play_file(white_noise_path)

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
    # Clamp brightness between -100 (full transparent) and 0 (full visible)
    brightness = max(-100, min(0, brightness + value))
    set_brightness(brightness)

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
    else:
        # Set brightness to -100 to black out the screen
        set_brightness(-100)
        pause()
    is_black_screen = not is_black_screen

def cycle_green_screen(direction):
    global current_green_index, current_file
    max_green_templates = 19
    # Only increase green index when already showing green
    # if coming from another channel show the green thats was selected lastly
    green_path = os.path.join(script_dir, 'assets', 'greenscreen', f'{current_green_index+1}.png')
    if current_file == green_path:
        # Wrap around index
        current_green_index = (current_green_index + direction) % (max_green_templates + 1)
        # Change path to new file
        green_path = os.path.join(script_dir, 'assets', 'greenscreen', f'{current_green_index+1}.png')
    play_file(green_path)

def check_keypresses():
    global tv_channel
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()  # Exit the program when the window is closed
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                print("keypress [UP]")
                seek(5)
            elif event.key == pygame.K_DOWN:
                print("keypress [DOWN]")
                seek(-5)
            elif event.key == pygame.K_UP and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT] + [UP]")
                pause()
                seek(.04)  # smaller than 0.2s: frame-by-frame
            elif event.key == pygame.K_DOWN and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT] + [DOWN]")
                pause()
                seek(-.04)  # smaller than 0.2s: frame-by-frame
            elif event.key == pygame.K_RIGHT:
                print("keypress [RIGHT]")
                next_channel()
            elif event.key == pygame.K_LEFT:
                print("keypress [LEFT]")
                prev_channel()
            elif event.key == pygame.K_SPACE or event.key == pygame.K_p:
                print("keypress [p]")
                toggle_play()
            elif event.key == pygame.K_ESCAPE:
                print("keypress [ESC]")
                toggle_fullscreen()
            elif event.key == pygame.K_q and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT] + [q]")
                close_program()
            elif event.key == pygame.K_q:
                print("keypress [q]")
                shutdown()
            elif event.key == pygame.K_b:
                print("keypress [b]")
                toggle_black_screen()
            elif event.key == pygame.K_g and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT][ + g]")
                cycle_green_screen(-1)
            elif event.key == pygame.K_g:
                print("keypress [g]")
                cycle_green_screen(1)
            elif event.key == pygame.K_c:
                print("keypress [c]")
                set_video_fitting()
            elif event.key == pygame.K_i and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT] + [i]")
                clear_inpoints(tv_channel)
            elif event.key == pygame.K_i:
                print("keypress [i]")
                set_inpoints(tv_channel)
            elif event.key == pygame.K_PERIOD:
                print("keypress [.] More brightness")
                adjust_video_brightness(5)
            elif event.key == pygame.K_COMMA:
                print("keypress [,] Less brightness")
                adjust_video_brightness(-5)
            elif event.key == pygame.K_a:
                print("keypress [a]")
                toggle_show_tv_gui()
            elif event.key == pygame.K_w and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress [SHIFT] + [w]")
                cycle_white_noise()
            elif event.key == pygame.K_w:
                print("keypress [w]")
                toggle_white_noise_on_channel_change()
            elif event.key == pygame.K_MINUS or (event.key == pygame.K_SLASH and pygame.key.get_mods() & pygame.KMOD_SHIFT) or pygame.key.name(event.key) == "[-]":
                print("keypress [-] Less volume")
                adjust_volume(-10)
            elif event.key == pygame.K_PLUS or (event.key == pygame.K_1 and pygame.key.get_mods() & pygame.KMOD_SHIFT) or pygame.key.name(event.key) == "[+]":
                print("keypress [+] More volume")
                adjust_volume(10)
            elif pygame.K_0 <= event.key <= pygame.K_9:
                print(f"keypress [number] {pygame.key.name(event.key)}")
                go_to_channel(event.key - pygame.K_0 - 1)  # -1 because pressing 1 should play file on key 0 not file key nr 1
            elif pygame.K_KP0 <= event.key <= pygame.K_KP9:
                print(f"keypress [number@numpad] {event.key}")
                go_to_channel(event.key - pygame.K_KP0 - 1)  # -1 because pressing 1 should play file on key 0 not file key nr 1
            else:
                print("other key: "+ pygame.key.name(event.key))



def prev_channel():
    global tv_channel
    # if current file as an in-point and current_time is bigger than that, skip to input and
    # pause() for resetting scene
    if inpoints[tv_channel] > 0 and get_current_video_position() > inpoints[tv_channel]:
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
        sleep(white_noise_duration)

    set_video_fitting(video_fittings[tv_channel])  # Set fit for this channel
    play_file(filelist[number], inpoints[number])

def play_file(file, inpoint=0.0):
    global mpv_process, current_file, ipc_socket_path
    if os.path.exists(ipc_socket_path):
        print(f"Swapping to new file: {os.path.basename(file)} at {inpoint} seconds.")
        # Use loadfile command to replace the video source without stopping mpv
        command = f'echo \'{{"command": ["loadfile", "{file}", "replace", "start={inpoint}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)

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

def set_inpoints(channel):
    global inpoints
    current_inpoint = get_current_video_position()
    inpoints[channel] = current_inpoint
    print(f"Set new inpoint for channel {channel}: {inpoints[channel]}")
    print(inpoints)

def clear_inpoints(channel):
    global inpoints
    inpoints[channel] = 0
    print(f"Cleard new inpoint for channel {channel}")
    print(inpoints)

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

    # Overlay-add command
    stride = width * 4  # BGRA has 4 bytes per pixel
    command = f'echo \'{{"command": ["overlay-add", {overlay_id}, {x}, {y}, "{image_path}", 0, "bgra", {width}, {height}, {stride}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
    subprocess.call(command, shell=True)

    # Cancel any existing overlay removal thread for this overlay_id
    if overlay_id in active_overlays:
        active_overlays[overlay_id].cancel()

    # Function to remove overlay after the duration
    def remove_overlay():
        sleep(display_duration)
        remove_command = f'echo \'{{"command": ["overlay-remove", {overlay_id}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(remove_command, shell=True)
        print(f"Removed overlay ID {overlay_id}")
    
    # Start a new thread to remove the overlay and store it
    thread = threading.Timer(display_duration, remove_overlay)
    thread.start()
    active_overlays[overlay_id] = thread

    print(f"Displaying image: {os.path.basename(image_path)} (@ID:{overlay_id}) at x={x} y={y} for {display_duration} seconds")


def update_inpoints():
    global inpoints
    inpoints = [0] * len(filelist)

def close_program():
    print("Close the program..")
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

def main():
    print("--------------------------------------------------------------------------------")
    pygame_init()
    player_init()
    system_init()

    while True:
        get_window_size()
        check_keypresses()

        # Update file list if USB is inserted or removed
        old_filelist = filelist.copy()
        update_files_from_usb()

        #print("compare filelist")
        if filelist != old_filelist:
            # USB drive was taken out or inserted again
            update_inpoints()
            print(f"filelist updated ({len(filelist)}):")
            print("  " + ("\n  ".join(f"Ch.{i+1} > {os.path.basename(file)}" for i, file in enumerate(filelist))))
            print("inpoints and video fitting reset:")
            reset_inpoints_video_fitting()
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
        sleep(0.1)

if __name__ == '__main__':
    main()
