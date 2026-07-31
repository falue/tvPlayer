# Raspberry Pi OS Lite — Migration Checklist

Target: Raspberry Pi OS Lite (64-bit, Bookworm), headless, no desktop environment.  
mpv renders directly via DRM/KMS on tty1.

---

## Flash & First Boot

- Flash **Raspberry Pi OS Lite (64-bit, Bookworm)** via Raspberry Pi Imager
- In Imager advanced settings: set hostname (eg. `tvPlayer`), enable SSH, configure WiFi, create user (e.g. `dp`)
- Boot, SSH in

---

## User & Groups

```bash
sudo usermod -aG video,input,gpio,render,audio dp
```

---

## Autologin on tty1

Required for DRM/KMS access without a display manager.

```bash
sudo raspi-config
# System Options → Auto Login → Console Autologin: Enable
```

---

## Install Packages

```bash
sudo apt update && sudo apt install -y \
  mpv libmpv-dev \
  python3-pip \
  git \
  ffmpeg imagemagick \
  mosquitto mosquitto-clients \
  udisks2 lsof
```

Enable WebSocket listener for the web remote (browsers can't use raw MQTT).
Declaring `listener 1883` is required — Mosquitto 2.0+ disables the default port when any `listener` is added:
```bash
sudo tee /etc/mosquitto/conf.d/websockets.conf >/dev/null <<'EOF'
listener 1883
listener 9001
protocol websockets
allow_anonymous true
EOF

sudo systemctl restart mosquitto
```

## USB Automount

OS Lite has no file manager to trigger USB mounting. `udisks2` handles it, but needs a polkit rule to allow mounting without an active desktop session:

```bash
sudo tee /etc/polkit-1/rules.d/10-udisks2-mount.rules >/dev/null <<'EOF'
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.udisks2.filesystem-mount" ||
         action.id == "org.freedesktop.udisks2.filesystem-mount-other-seat" ||
         action.id == "org.freedesktop.udisks2.filesystem-mount-system") &&
        subject.user == "<YOUR_USERNAME>") {
        return polkit.Result.YES;
    }
});
EOF
```

## Optionals
### Hide kernel messages
Edit:
```
sudo nano /boot/firmware/cmdline.txt
```
Append (all on one line):
```
quiet loglevel=0 systemd.show_status=0 rd.systemd.show_status=0 vt.global_cursor_default=0 logo.nologo splash
```

### Change CLI font size
```
sudo dpkg-reconfigure console-setup
```
Choose
- `UTF-8`
- `Guess optimal character set`
- Choose font `Terminus` and size to `16x32` (for fuzzy or TVs)

### Custom splash image
```
sudo apt install plymouth plymouth-themes
```
And see here for installation: `assets/splashscreen/README.md`

---

## Clone repo
```
git clone https://github.com/falue/tvPlayer.git
```


## Python Dependencies

```bash
pip install --break-system-packages python-mpv evdev natsort paho-mqtt flask RPi.GPIO Pillow
```

> `--break-system-packages` is required on Bookworm+ (PEP 668). Safe here since this is a single-purpose device.

---

## Network / Hotspot (RaspAP)

Install RaspAP:
```bash
curl -sL https://install.raspap.com | bash
```

During the installer, choose:
- **Complete installation** — yes
- **Set default config for hostapd** — yes
- **Enable HttpOnly for session cookies** — yes
- **Enable control service** — yes
- **Install Ad-blocking** — no
- **Install OpenVPN** — no
- **Install WireGuard** — no
- **Install RestAPI** — no
- **Enable VPN provider client** — no
- **Enable TCP BBR congestion control** — yes

After reboot, RaspAP creates a WiFi AP with default SSID `raspi-webgui`.

### Fix: NetworkManager vs hostapd conflict

If `wlan0` stays in `type managed` instead of `type AP`, NetworkManager is fighting hostapd for the interface. This happens when a saved Wi-Fi client profile auto-reconnects.

**1. Disable autoconnect of the old Wi-Fi client profile:**
```bash
sudo nmcli connection modify netplan-wlan0-<SSID> connection.autoconnect no
sudo nmcli connection down netplan-wlan0-<SSID>
```

**2. Tell NetworkManager to completely ignore wlan0:**
```bash
sudo mkdir -p /etc/NetworkManager/conf.d

sudo tee /etc/NetworkManager/conf.d/10-unmanaged-wlan0.conf >/dev/null <<'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan0
EOF

sudo systemctl restart NetworkManager
```

**3. Reset the interface and restart hostapd (one-time, not needed after reboot):**
```bash
sudo ip link set wlan0 down
sudo ip addr flush dev wlan0
sudo ip link set wlan0 up
sudo systemctl restart hostapd
```

**4. Verify:**
```bash
iw dev
```
Expected: `type AP` and `ssid RaspAP` (not `type managed`).

> After reboot, hostapd should automatically bring up `wlan0` as AP with IP `10.3.141.1`. Verify with a reboot.

## Configure the RaspAP
Configure via the RaspAP admin panel at `http://10.3.141.1` from another device. 
> RaspAP admin panel login default: user `admin`, password `secret` — change pw to eg `digitalProps#8400`

- **Hotspot → Basic**: SSID = `tvPlayer`, Security = WPA2
- **Hotspot → Security**: set a password
- **DHCP Server**: leave defaults (clients get `10.3.141.x`)

The tvPlayer web remote will then be available at `http://10.3.141.1:8080` from any device connected to the `tvPlayer` WiFi.


---

## Systemd Service

```
sudo nano /etc/systemd/system/tvplayer.service
```
```ini
[Unit]
Description=tvPlayer
After=multi-user.target

[Service]
User=dp
WorkingDirectory=/home/dp/tvPlayer
ExecStart=/usr/bin/python3 -u tvPlayer.py
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable tvplayer.service
```

---

## Verify DRM Works

```bash
mpv --vo=drm --drm-connector=HDMI-A-1 /path/to/test.mp4
```

If this plays fullscreen without X, the base system is ready.

---

## Refactor Steps (after OS is ready)

1. Replace pygame + socat IPC → python-mpv
2. Disable all mpv built-in UI (osc, osd, keybinds)
3. Replace pygame keyboard → evdev thread
4. Configure `vo=drm`, systemd service on tty1
5. Multi-HDMI hotplug (EDID poll, connector select)
6. Overlay routing via python-mpv
7. Multi-monitor: one process, multiple players, per-screen state
