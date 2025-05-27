#!/bin/bash

# Check if the script is run as root (with sudo)
if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root. Please run it using sudo."
  exit 1
fi

# ASK USER FOR PREFERENCES AT THE START
read -p "Do you want to run 'sudo apt-get update'? (Y/n): " run_update
run_update=${run_update,,}  # Convert to lowercase

read -p "Do you want to create a desktop shortcut file? (Y/n): " create_desktop
create_desktop=${create_desktop,,}  # Convert to lowercase

read -p "Do you want to create an autostart file? (Y/n): " create_autostart
create_autostart=${create_autostart,,}  # Convert to lowercase

if [[ "$create_autostart" == "y" ]]; then
    read -p "Autostart with a dialog to confirm? Otherwise, start the script directly. (Y/n): " with_dialog
    with_dialog=${with_dialog,,}  # Convert to lowercase
fi

read -p "Try to disable 'removable medium is inserted' pop-up? (Y/n): " disable_popup
disable_popup=${disable_popup,,}  # Convert to lowercase

# Default behavior for inputs: if nothing is entered, assume "yes"
run_update=${run_update:-y}
create_desktop=${create_desktop:-y}
create_autostart=${create_autostart:-y}
with_dialog=${with_dialog:-y}
disable_popup=${disable_popup:-y}

# RUN APT-GET UPDATE IF USER AGREES
if [[ "$run_update" == "y" ]]; then
    echo "Updating package list..."
    sudo apt-get update
else
    echo "Skipping 'apt-get update'..."
fi

# Get the full path of the script to be executed
USER_HOME=$(getent passwd $SUDO_USER | cut -d: -f6)
SCRIPT_PATH="$(realpath $0)"
SCRIPT_LOCATION="$(dirname $SCRIPT_PATH)"
EXCEC_PATH_MAIN="$SCRIPT_LOCATION/start.sh"
FULL_ICON_PATH="$SCRIPT_LOCATION/assets/icon.png"

# Set up virtual environment
### TODOOOOOO maybe manually....
echo "Creating virtual environment from normal user.."
REAL_USER=$(logname 2>/dev/null || echo "$SUDO_USER")
##### sudo -u "$REAL_USER" python3 -m venv venv
##### source "$SCRIPT_LOCATION/venv/bin/activate"

# Install mpv and socat
echo "Installing mpv and socat..."
sudo apt-get install -y mpv socat wmctrl

# Install Python packages from requirements.txt
# Detect Debian version and install Python packages accordingly
debian_version=$(cat /etc/debian_version)
if [[ "$debian_version" == 12* ]]; then
    echo "Installing Python libraries using apt (Debian Bookworm)..."
    sudo apt install -y python3-pip
    sudo apt-get install -y $(grep -oP '^.*(?==)' requirements.txt | tr '\n' ' ')
else
    echo "Installing Python libraries using pip (Debian Bullseye)..."
    pip install -r requirements.txt
fi

# Make the Python script executable
chmod +x "$EXCEC_PATH_MAIN"

# CREATE DESKTOP SHORTCUT IF USER AGREES
if [[ "$create_desktop" == "y" ]]; then
    ## CREATE SHORTCUT FILE ON DESKTOP
    DESKTOP_SHORTCUT_FILE="$USER_HOME/Desktop/tvPlayer.desktop"  # Define the path to the desktop
    cat > "$DESKTOP_SHORTCUT_FILE" << EOL
[Desktop Entry]
Type=Application
Name=tvPlayer
Exec=bash $EXCEC_PATH_MAIN
Icon=$FULL_ICON_PATH
X-LXDE-Startup=true
EOL
    # Make the desktop file executable
    chmod +x "$DESKTOP_SHORTCUT_FILE"
    echo "Desktop shortcut created at $DESKTOP_SHORTCUT_FILE"
else
    echo "Skipping desktop shortcut creation..."
fi

# CREATE AUTOSTART FILE IF USER AGREES
if [[ "$create_autostart" == "y" ]]; then
    AUTOSTART_PATH="$USER_HOME/.config/autostart"
    if [[ "$with_dialog" == "y" ]]; then
        AUTOSTART_SCRIPT_NAME="tvPlayer-startdialog"
        EXEC_AUTOSTART_COMMAND="bash $SCRIPT_LOCATION/autostart-dialog.sh"
        FULL_ICON_PATH="$SCRIPT_LOCATION/assets/icon_autostart.png"
        AUTOSTART_FILE_PATH="$AUTOSTART_PATH/tvPlayer-startdialog.desktop"
    else
        AUTOSTART_SCRIPT_NAME="tvPlayer"
        EXEC_AUTOSTART_COMMAND="bash $SCRIPT_LOCATION/start.sh"
        FULL_ICON_PATH="$SCRIPT_LOCATION/assets/icon.png"
        AUTOSTART_FILE_PATH="$AUTOSTART_PATH/tvPlayer.desktop"
    fi
    # Create the autostart directory if it doesn't exist
    mkdir -p "$AUTOSTART_PATH"
    # Create the .desktop file in autostart
    cat > "$AUTOSTART_FILE_PATH" << EOL
[Desktop Entry]
Type=Application
Name=$AUTOSTART_SCRIPT_NAME
Exec=$EXEC_AUTOSTART_COMMAND
Icon=$FULL_ICON_PATH
X-LXDE-Startup=true
EOL
    # Make the desktop file executable
    chmod +x "$AUTOSTART_FILE_PATH"
    echo "Autostart file created at $AUTOSTART_FILE_PATH"
else
    echo "Skipping autostart file creation..."
fi

# DISABLE THE "REMOVABLE MEDIUM IS INSERTED" POP-UP IF USER AGREES
if [[ "$disable_popup" == "y" ]]; then
    PCMANFM_CONF="$USER_HOME/.config/pcmanfm/LXDE-pi/pcmanfm.conf"
    echo "PCManFM Config Path: $PCMANFM_CONF"

    if [ -f "$PCMANFM_CONF" ]; then
        # Check if the mount_open line exists
        if grep -q "mount_open=" "$PCMANFM_CONF"; then
            # Modify the existing line
            sed -i '/\[volume\]/,/\[/{s/mount_open=1/mount_open=0/}' "$PCMANFM_CONF"
        else
            # Add the mount_open line if it doesn't exist
            sed -i '/\[volume\]/a mount_open=0' "$PCMANFM_CONF"
        fi
    else
        # Create the config file if it doesn't exist
        mkdir -p "$USER_HOME/.config/pcmanfm/LXDE-pi"
        cat > "$PCMANFM_CONF" << EOL
[volume]
mount_open=0
autorun=0
EOL
    fi
    echo "Disabled 'removable medium is inserted' pop-up in PCManFM."
else
    echo "Skipping attempt to disable 'removable medium is inserted' pop-up..."
fi

echo "Installation complete. The script will now run on startup!"
