#!/bin/bash

# Check if the script is run as root (with sudo)
if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root. Please run it using sudo."
  exit 1
fi

# Update package list
echo "Updating package list..."
sudo apt-get update

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

# Get the full path of the script to be executed
USER_HOME=$(getent passwd $SUDO_USER | cut -d: -f6)
SCRIPT_PATH="$(realpath $0)"
SCRIPT_LOCATION="$(dirname $SCRIPT_PATH)"
EXCEC_PATH_MAIN="$SCRIPT_LOCATION/tvPlayer.py"
FULL_ICON_PATH="$SCRIPT_LOCATION/assets/icon.png"

# Make the Python script executable
chmod +x "$EXCEC_PATH_MAIN"

## CREATE SHORTCUT FILE ON DESKTOP
# Create the .desktop file for autostart
DESKTOP_SHORTCUT_FILE="$USER_HOME/Desktop/tvPlayer.desktop"  # Define the path to the desktop
cat > "$DESKTOP_SHORTCUT_FILE" << EOL
[Desktop Entry]
Type=Application
Name=tvPlayer
Exec=sudo python3 $EXCEC_PATH_MAIN
Icon=$FULL_ICON_PATH
X-LXDE-Startup=true
EOL
# Make the desktop file executable
chmod +x "$DESKTOP_SHORTCUT_FILE"
echo "Desktop shortcut created at $DESKTOP_SHORTCUT_FILE"

## CREATE FILE IN .config autostart
EXEC_AUTOSTART_PATH="$SCRIPT_LOCATION/autostart.sh"
# Create the autostart directory if it doesn't exist
AUTOSTART_PATH="$USER_HOME/.config/autostart"
FULL_ICON_PATH="$SCRIPT_LOCATION/assets/icon_autostart.png"
mkdir -p "$AUTOSTART_PATH"
# Create the .desktop file for autostart
AUTOSTART_FILE_PATH="$AUTOSTART_PATH/tvPlayer-startdialog.desktop"
cat > "$AUTOSTART_FILE_PATH" << EOL
[Desktop Entry]
Type=Application
Name=tvPlayer-startdialog
Exec=sudo bash $EXEC_AUTOSTART_PATH
Icon=$FULL_ICON_PATH
X-LXDE-Startup=true
EOL
# Make the desktop file executable
chmod +x "$AUTOSTART_FILE_PATH"
echo "Autostart file created at $AUTOSTART_FILE_PATH"

# Disable the "removable medium is inserted" pop-up in PCManFM
# FIXME: DOES NOT WORK. DOES NOT DISABLE THE THING.
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

echo "Installation complete. The script will now run on startup!"
