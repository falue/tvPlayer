import os
import sys
import pygame
import subprocess
import json
from time import sleep

""" 
TODO
- no black window between channel switching
- make autostart
- toggle video size between contain (letterboxed), stretch and cover
- display channel number
- in points on each file
- display white noise inbetween videos when tv_white_noise_on_channel_change
 """

# Customizing
tv_animations = False
tv_white_noise_on_channel_change = False
tv_channel_offset = 0  # display higher channel nr than actually available

# Leave me be
tv_channel = 0
playing = False
filelist = []
inpoints = []
mpv_process = None  # Global variable to track the running mpv process

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
    global filelist, inpoints
    filelist = []
    inpoints = []

    if os.path.exists(usb_root):
        for device in os.listdir(usb_root):
            device_path = os.path.join(usb_root, device)
            if os.path.isdir(device_path):
                try:
                    for file in os.listdir(device_path):
                        if file.endswith(('.mp4', '.mkv', '.avi')) and not file.startswith('.'):
                            filelist.append(os.path.join(device_path, file))
                            inpoints.append(0)  # Initialize inpoints to 0 for each file
                except PermissionError:
                    print(f"Permission denied while accessing: {device_path}. Ignoring this device.")
                    stop_video()
                    filelist = []
                    inpoints = []
                    continue  # Skip this device if it's no longer accessible
                except FileNotFoundError:
                    print(f"Device {device_path} was removed. Ignoring this device.")
                    stop_video()
                    filelist = []
                    inpoints = []
                    continue


def show_white_noise():  # (duration)
    # Launch mpv to play the video
    play_file(os.path.join(script_dir, 'assets', 'white_noise.mp4'))

""" def show_blank_screen(duration):
    # Display a blank screen for the specified duration
    screen.fill((0, 0, 0))  # Black screen using pygame
    pygame.display.update()
    sleep(duration / 1000) """

def check_keypresses():
    global playing, tv_channel
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
            elif event.key == pygame.K_RIGHT:
                print("keypress K_RIGHT")
                seek(5)
            elif event.key == pygame.K_LEFT:
                print("keypress K_LEFT")
                seek(-5)
            elif event.key == pygame.K_SPACE or event.key == pygame.K_p:
                print("keypress K_p")
                toggle_play()
            elif event.key == pygame.K_ESCAPE:
                print("keypress K_ESCAPE")
                toggle_fullscreen()
            elif event.key == pygame.K_i:
                print("keypress K_i")
                set_inpoints(tv_channel)
            elif pygame.K_0 <= event.key <= pygame.K_9:
                print("keypress number "+ pygame.key.name(event.key))
                go_to_channel(event.key - pygame.K_0)
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
    global tv_channel, playing

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

def play_file(file, inpoint=0):
    global playing, mpv_process
    playing = True

    # Ensure inpoint is a valid number (default to 0 if invalid)
    if inpoint is None or not isinstance(inpoint, (int, float)) or inpoint < 0:
        inpoint = 0

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

    print(f"Play file: {file}")


def toggle_play():
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command
    if os.path.exists(ipc_socket_path):
        # Send the pause command to the running mpv instance via IPC
        command = 'echo \'{"command": ["cycle", "pause"]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
    else:
        print("mpv IPC socket not found.")

def stop_video():
    global playing, mpv_process
    playing = False
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command

    if mpv_process is not None and os.path.exists(ipc_socket_path):
        print("Stopping video and making screen black...")
        # Send a loadfile null command to stop playback and clear the screen
        command = 'echo \'{"command": ["loadfile", "null", "replace"]}\' | socat - UNIX-CONNECT:' + ipc_socket_path + ' > /dev/null 2>&1'
        subprocess.call(command, shell=True)
    else:
        print("mpv IPC socket not found or mpv process not running.")


def toggle_fullscreen():
    pygame.display.toggle_fullscreen()

def seek(seconds):
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command
    if os.path.exists(ipc_socket_path):
        # Create the command to send a seek command to the running mpv instance via IPC
        command = f'echo \'{{"command": ["seek", {seconds}, "relative"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path} > /dev/null 2>&1'
        subprocess.call(command, shell=True)
        print(f"Seeking {seconds} seconds")
    else:
        print("mpv IPC socket not found.")

def set_inpoints(channel):
    global inpoints
    current_inpoint = get_current_video_position()
    inpoints[channel] = current_inpoint
    print("set new inpoint for channel " + channel + ":")
    print(inpoints)


def get_current_video_position():
    ipc_socket_path = '/tmp/mpv_socket'  # Same as the one used in the subprocess command
    if os.path.exists(ipc_socket_path):
        # Send the command to get the current playback time
        command = f'echo \'{{"command": ["get_property", "time-pos"]}}\' | socat - UNIX-CONNECT:{ipc_socket_path}'
        # Run the command and capture the output
        result = subprocess.check_output(command, shell=True).decode('utf-8').strip()
        
        try:
            # Parse the result as JSON and extract the playback position
            response = json.loads(result)
            if "data" in response:
                return response["data"]  # Current position in seconds
            else:
                return 0  # Default if no position is available
        except json.JSONDecodeError:
            print("Failed to parse mpv response")
            return 0
    else:
        print("mpv IPC socket not found.")
        return 0

def show_channel_number(number):
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

def main():
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("--------------------------------------------------------------------------------")
    print("start!")
    global playing

    print("get usb root")
    detect_usb_root()
    print("get filelist")
    update_files_from_usb()
    print("initial filelist:")
    print(filelist)
    print("initial inpoints:")
    print(inpoints)

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
            update_inpoints()
            print("filelist updated:")
            print(filelist)
            print("inpoints updated:")
            print(inpoints)
            if tv_animations:
                #stop white noise video
                stop_video()

        # If no files found, show white noise or blank screen
        if not filelist:
            if tv_animations:
                print("No files available - show white noise")
                if not playing:
                    show_white_noise()
            else:
                print("No files available - show blank screen")

        # Automatically play video when filelist is populated
        if filelist and not playing:
            
            print("start video")
            go_to_channel(0)

        #print("update pygame")
        pygame.display.update()
        sleep(0.1)

if __name__ == '__main__':
    main()
