#!/bin/bash

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install mpv and socat
echo "Installing mpv and socat..."
sudo apt-get install -y mpv socat

# Install Python packages from requirements.txt
echo "Installing Python libraries..."
pip install -r requirements.txt

# Get the full path of the script to be executed
USER_HOME=$(getent passwd $SUDO_USER | cut -d: -f6)
SCRIPT_PATH="$(realpath $0)"
SCRIPT_DIR="$(dirname $SCRIPT_PATH)"
SCRIPT_NAME="tvPlayer.py"
FULL_SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_NAME"

# Make the Python script executable
chmod +x "$FULL_SCRIPT_PATH"

# Create the autostart directory if it doesn't exist
AUTOSTART_DIR="$USER_HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

# Create the .desktop file for autostart
DESKTOP_FILE="$AUTOSTART_DIR/tvPlayer.desktop"
DESKTOP_PATH="$USER_HOME/Desktop/tvPlayer.desktop"  # Define the path to the desktop

echo "Creating autostart file..."
cat > "$DESKTOP_FILE" << EOL
[Desktop Entry]
Type=Application
Name=tvPlayer
Exec=python3 $FULL_SCRIPT_PATH
X-LXDE-Startup=true
EOL

echo "Autostart file created at $DESKTOP_FILE"

# Copy the .desktop file to the desktop
cp "$DESKTOP_FILE" "$DESKTOP_PATH"

# Make the desktop file executable
chmod +x "$DESKTOP_PATH"

echo "Desktop shortcut created at $DESKTOP_PATH"

# Disable the "removable medium is inserted" pop-up in PCManFM
PCMANFM_CONF="$USER_HOME/.config/pcmanfm/LXDE-pi/pcmanfm.conf"
echo "PCManFM Config Path: $PCMANFM_CONF"

if [ -f "$PCMANFM_CONF" ]; then
    # Modify the existing config file
    sed -i '/\[volume\]/,/\[/{s/mount_open=1/mount_open=0/}' "$PCMANFM_CONF"
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
