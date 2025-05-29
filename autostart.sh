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

# Display a Zenity dialog
WINDOW_WIDTH=450  # Width of the Zenity dialog
zenity --question \
    --timeout=12 \
    --width=$WINDOW_WIDTH \
    --title="Dialog tvPlayer-autostart" \
    --text="Do you want to close all applications and start tvPlayer? \nAutostart in 12 seconds.." \
    --ok-label="Start tvPlayer, close everything else" \
    --cancel-label="Ignore" &

# Give Zenity some time to start
sleep .5  # increase the sleep duration if necessary

# Get the Zenity window ID by matching the class "zenity.Zenity"
# ZENITY_WINDOW_ID=$(wmctrl -lx | grep "Dialog tvPlayer-autostart" | awk '{print $1}')
ZENITY_WINDOW_ID=$(wmctrl -lx | grep "zenity.Zenity" | awk '{print $1}')

# Check if the Zenity window ID was found
if [ -n "$ZENITY_WINDOW_ID" ]; then
    # Get screen resolution using xrandr
    SCREEN_WIDTH=$(xrandr | grep '*' | awk '{print $1}' | cut -d'x' -f1)
    
    if [ -n "$SCREEN_WIDTH" ]; then
        # Calculate the X coordinate to center the window horizontally
        X_POS=$(( (SCREEN_WIDTH - WINDOW_WIDTH) / 2 ))
        
        # Move the Zenity window to center horizontally and 75px from the top
        wmctrl -i -r "$ZENITY_WINDOW_ID" -e 0,$X_POS,75,-1,-1
        echo "Zenity window moved to $X_POS, 75."
    else
        echo "Error: Screen width not found. Zenity window will not be moved."
    fi
else
    echo "Zenity window ID not found. Skipping window move."
fi

# Wait for Zenity to finish and get the exit status
wait $!
response=$?

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
    echo "Cancel clicked, doing nothing."
fi
