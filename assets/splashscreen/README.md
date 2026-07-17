# Install a splash screen

# Copy the theme folder to:
sudo cp -r tvPlayer /usr/share/plymouth/themes/

# Enable it:
sudo plymouth-set-default-theme -R tvPlayer

# Reboot:
sudo reboot