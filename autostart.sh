#!/bin/bash

# Set the terminal window title (debug)
echo -ne "\033]0;tvPlayer Startup Script\007"

# Function to close only visible, user-opened windows
close_all_visible_windows() {
    # List all visible windows with extended information (including class)
    wmctrl -lx | while read -r window; do
        window_id=$(echo $window | awk '{print $1}')
        window_class=$(echo $window | awk '{print $3}')
        window_title=$(echo "$window" | awk '{$1=$2=$3=$4=""; print $0}' | sed 's/^ *//')

        # Filter to exclude system-critical windows based on their class
         if [[ "$window_class" != *"lxpanel.Lxpanel"* ]] && \
            [[ "$window_class" != *"x-terminal-emulator.X-terminal-emulator"* ]] && \
            [[ "$window_class" != "pcmanfm.Pcmanfm" || "$window_title" != "pcmanfm" ]]; then
            echo "Closing visible window ID: '$window_title' ($window_class) [$window_id]"
            # Close the window (if visible), suppress errors
            wmctrl -ic "$window_id" 2>/dev/null || true
        else
            echo "Skipping system window: '$window_title' ($window_class) [$window_id]"
        fi
    done
}

# Display a Zenity dialog with a countdown and options
zenity --question --timeout=12 --width=450 --title="Start tvPlayer?" --text="Do you want to close all applications and start tvPlayer? \nAutostart in 12 seconds.." --ok-label="Start tvPlayer, close everything else" --cancel-label="Ignore"

# Get the exit status of Zenity dialog
response=$?

# Path to the .desktop file
desktop_file="/home/pi/Desktop/tvPlayer.desktop"

# Response handling:
if [ "$response" -eq 0 ] || [ "$response" -eq 5 ]; then
    # OK clicked or timeout, close all visible windows and start tvPlayer
    echo "OK or Timeout, closing all visible windows and starting tvPlayer..."

    # Close all visible windows in the background
    ( sleep 1; close_all_visible_windows ) &

    sleep 2
    # Get the directory of the currently running script (autorun.sh)
    script_dir=$(dirname "$(realpath "$0")")
    # Run the Python script using the directory of this script
    python3 "$script_dir/tvPlayer.py" &

else
    # Cancel clicked, do nothing
    echo "Cancel clicked, doing nothing."
fi
