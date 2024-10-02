import os
import sys
import pygame
import subprocess
import json
from time import sleep
from natsort import natsorted

""" 
TODO
- tv_animations:
    - tv_animations: show number of channels top right
    - tv_white_noise_on_channel_change: white noise in between channel switching
- plus/minus for volume animation / real volume control? scene 45 "turns the volume down"
- reduce brightness manually incremental by pressing alt+number, eg. alt+4 means 40% etc
- has sound on hdmi?
- if tv animation swap channel - show_white_noise() then sleep(1) then next video swap?
- enable/disable "TV animations" by pressing "t"
- white nmoise always stretch to screen; reset befiore another file plays
- video_fitting is same for all files. should be a per-video-setting
 """

# Customizing
tv_animations = True  # show number of channels top right
tv_white_noise_on_channel_change = True  # white noise in between channel switching
tv_channel_offset = 0  # display higher channel nr than actually available

# Leave me be
tv_channel = 0
# playing = False
filelist = []
inpoints = []
mpv_process = None  # Global variable to track the running mpv process
fitting_modes = ['contain', 'stretch', 'cover']  # List of fitting modes
current_fitting_index = 0  # Start with 'contain'
is_black_screen = False
current_file = ""

# Initialize pygame for keyboard input and fullscreen handling
pygame.init()
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
pygame.display.set_caption('tvPlayer')
pygame.mouse.set_visible(False)  # Hide the mouse cursor

# Get the window ID to pass to mpv
window_info = pygame.display.get_wm_info()
window_id = window_info['window']  # Get the window ID for embedding mpv

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
    global filelist #, inpoints
    filelist = []  # Resets always

    if os.path.exists(usb_root):
        for device in os.listdir(usb_root):
            device_path = os.path.join(usb_root, device)
            if os.path.isdir(device_path):
                try:
                    for file in os.listdir(device_path):
                        if file.endswith(('.mp4', '.mkv', '.avi', '.mxf', '.mov', '.MP4', '.MKV', '.AVI', '.MXF', '.MOV')) and not file.startswith('.'):
                            filelist.append(os.path.join(device_path, file))
                            # inpoints.append(0)  # Initialize inpoints to 0 for each file
                except PermissionError:
                    print(f"Permission denied while accessing: {device_path}. Ignoring this device.")
                    filelist = []
                    continue  # Skip this device if it's no longer accessible
                except FileNotFoundError:
                    print(f"Device {device_path} was removed. Ignoring this device.")
                    filelist = []
                    continue
        # Sort list naturally - 1.mp4, 2.mp4, 11.mp4 instead of 1.mp4, 11.mp4, 2.mp4
        # filelist = natsorted(filelist)  # case sensitive
        filelist = natsorted(filelist, key=lambda x: x.lower())  # case insensitive

def reset_inpoints():
    global inpoints
    inpoints = [0] * len(filelist)  # Create a list of zeros with the same length as filelist

def show_white_noise():  # (duration)
    global current_file
    # Launch mpv to play the video if  not already playing
    white_noise_path = os.path.join(script_dir, 'assets', 'white_noise.mp4')
    if not current_file == white_noise_path:
        play_file(white_noise_path)

def set_brightness(value):
    ipc_socket_path = '/tmp/mpv_socket'

    if os.path.exists(ipc_socket_path):
        command = f'echo \'{{"command": ["set_property", "brightness", {value}]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Set brightness to {value}")
    else:
        print("mpv IPC socket not found.")

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
    
    # Toggle the state
    is_black_screen = not is_black_screen

def check_keypresses():
    global tv_channel
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()  # Exit the program when the window is closed
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                print("keypress K_UP")
                next_channel()
            elif event.key == pygame.K_DOWN:
                print("keypress K_DOWN")
                prev_channel()
            elif event.key == pygame.K_RIGHT and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress K_RIGHT and SHIFT")
                pause()
                seek(.04)  # smaller than 0.2s: frame-by-frame
            elif event.key == pygame.K_RIGHT:
                print("keypress K_RIGHT")
                seek(5)
            elif event.key == pygame.K_LEFT and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress K_LEFT and SHIFT")
                pause()
                seek(-.04)  # smaller than 0.2s: frame-by-frame
            elif event.key == pygame.K_LEFT:
                print("keypress K_LEFT")
                seek(-5)
            elif event.key == pygame.K_SPACE or event.key == pygame.K_p:
                print("keypress K_p")
                toggle_play()
            elif event.key == pygame.K_ESCAPE:
                print("keypress K_ESCAPE")
                toggle_fullscreen()
            elif event.key == pygame.K_q:
                print("keypress K_q")
                shutdown()
            elif event.key == pygame.K_b:
                print("keypress K_b")
                toggle_black_screen()
            elif event.key == pygame.K_c:
                print("keypress K_c")
                # FIXME:
                video_fitting()
            elif event.key == pygame.K_i and pygame.key.get_mods() & pygame.KMOD_SHIFT:
                print("keypress K_i and SHIFT")
                clear_inpoints(tv_channel)
            elif event.key == pygame.K_i:
                print("keypress K_i")
                set_inpoints(tv_channel)
            elif pygame.K_0 <= event.key <= pygame.K_9:
                print("keypress number "+ pygame.key.name(event.key))
                go_to_channel(event.key - pygame.K_0 - 1)  # -1 because pressing 1 should play file on key 0 not file key nr 1
            else:
                print("other key: "+ pygame.key.name(event.key))

def prev_channel():
    global tv_channel
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

    if number >= len(filelist):
        number = 0
    if number < 0:
        number = len(filelist) - 1

    tv_channel = number

    if tv_animations:
        if tv_white_noise_on_channel_change:
            print("show_white_noise in between")
            #show_white_noise(200)
        else:
            print("show show_blank_screen in between")
            # FIXME: if had video files playing and USB is removed, video keeps playing if short enough
        show_channel_number(tv_channel + tv_channel_offset)

    play_file(filelist[number], inpoints[number])

def play_file(file, inpoint=0.0):
    global mpv_process, current_file
    
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command

    if mpv_process is not None and os.path.exists(ipc_socket_path):
        print(f"Swapping to new file: {file} at {inpoint} seconds.")
        # Use loadfile command to replace the video source without stopping mpv
        command = f'echo \'{{"command": ["loadfile", "{file}", "replace", "start={inpoint}"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
    else:
        print("Starting mpv process for the first time.")
        # Command to play video in fullscreen using mpv
        command = [
            'mpv', '--loop-file', '--start=' + str(inpoint), '--fs', '--quiet',
            '--no-input-terminal', '--input-ipc-server=' + ipc_socket_path, '--wid=' + str(window_id), file
        ]
        
        # Execute the command and store the process
        mpv_process = subprocess.Popen(command)

    current_file = file
    play()  # if paused, resume anyways FIXME: makes file stutter if playing already
    print(f"Play file: {file}")

def play():
    is_paused = get_mpv_property("pause")
    if is_paused is not None and is_paused:
        ipc_socket_path = '/tmp/mpv_socket'
        command = 'echo \'{"command": ["set_property", "pause", false]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print("Video playing.")
    elif is_paused is False:
        print("Video is already playing.")


def pause():
    ipc_socket_path = '/tmp/mpv_socket'
    if os.path.exists(ipc_socket_path):
        command = 'echo \'{"command": ["set_property", "pause", true]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print("Video paused.")
    else:
        print("mpv IPC socket not found.")

def toggle_play():
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command
    if os.path.exists(ipc_socket_path):
        # Send the pause command to the running mpv instance via IPC
        command = 'echo \'{"command": ["cycle", "pause"]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
    else:
        print("mpv IPC socket not found.")

""" def stop_video():
    global mpv_process
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command

    if mpv_process is not None and os.path.exists(ipc_socket_path):
        print("Stopping video and making screen black...")
        # Send a loadfile null command to stop playback and clear the screen
        command = 'echo \'{"command": ["loadfile", "null", "replace"]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
    else:
        print("mpv IPC socket not found or mpv process not running.") """

def toggle_fullscreen():
    pygame.display.toggle_fullscreen()

def seek(seconds):
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command
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
    ipc_socket_path = '/tmp/mpv_socket'
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


def video_fitting():
    global current_fitting_index
    # Update fitting mode index
    current_fitting_index = (current_fitting_index + 1) % len(fitting_modes)
    new_mode = fitting_modes[current_fitting_index]

    ipc_socket_path = '/tmp/mpv_socket'
    if os.path.exists(ipc_socket_path):
        if new_mode == 'contain':
            keepaspect = "yes"
            zoom_factor = 0
        elif new_mode == 'stretch':
            keepaspect = "no"
            zoom_factor = 0
        elif new_mode == 'cover':
            # Cover mode: calculate zoom based on video height and window height
            keepaspect = "yes"
            
            # Get current video height and window height
            video_height = get_mpv_property("height")
            window_height = get_mpv_property("osd-dimensions/h")
            # FIXME: Trial and error value 0.91. Mathematically correct would be 1.0
            #        But somehow I get letterboxes with 1.0
            zoom_factor = window_height / video_height - 0.91

        zoom_command = f'echo \'{{"command": ["set_property", "video-zoom", "{zoom_factor}"]}}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        command = f'echo \'{{"command": ["set_property", "keepaspect", "{keepaspect}"]}}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(zoom_command, shell=True)
        subprocess.call(command, shell=True)
        print(f"Toggled video fitting mode: {new_mode} with zoom {zoom_factor}")
    else:
        print("mpv IPC socket not found.")


def show_channel_number(number):
    # FIXME: draws behind video.
    # TODO: use mpvs logo setting to be used instead?
    # Load the PNG image from the channel_numbers directory
    image_path = os.path.join(script_dir, 'assets', 'channel_numbers', f'{number}.png')
    
    # Load the image as a surface
    channel_image = pygame.image.load(image_path)

    # Get the screen's width and height
    screen_width, screen_height = screen.get_size()

    # Calculate the position for the top-right corner
    image_rect = channel_image.get_rect()
    top_right_position = (screen_width - image_rect.width, 0)  # Top-right corner position

    # Blit the image onto the screen at the top-right position
    screen.blit(channel_image, top_right_position)

    # Update the part of the screen where the image was blitted
    pygame.display.update(pygame.Rect(top_right_position, (image_rect.width, image_rect.height)))

    print(f"Showing channel number image: {image_path}")

def update_inpoints():
    global inpoints
    inpoints = [0] * len(filelist)

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
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("start!")

    print("get usb root")
    detect_usb_root()
    print("get filelist")
    update_files_from_usb()
    reset_inpoints()
    print("initial filelist:")
    print(filelist)
    print("initial inpoints:")
    print(inpoints)

    print("start video initially ")
    go_to_channel(0)

    while True:
        #print("----")
        #print("keypresses")
        check_keypresses()

        # Update file list if USB is inserted or removed
        #print("copy filelist")
        old_filelist = filelist.copy()
        update_files_from_usb()

        #print("compare filelist")
        if filelist != old_filelist:
            # USB drive was taken out or inserted again
            update_inpoints()
            print("filelist updated:")
            print(filelist)
            print("inpoints updated:")
            reset_inpoints()
            print(inpoints)
            # start first video
            go_to_channel(0)

        # If no files found, show white noise or blank screen
        if not filelist:
            if tv_animations:
                print("No files available - show white noise")
                # if not playing:
                # todo: if USB teared oput, this is still true i guess?
                show_white_noise()
            else:
                print("No files available - show blank screen")

        # Automatically play video when filelist is populated
        """ if filelist and not playing:
            print("start video")
            go_to_channel(0) """

        #print("update pygame")
        pygame.display.update()
        sleep(0.1)

if __name__ == '__main__':
    main()
