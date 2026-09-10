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
After=multi-user.target user@1000.service
StartLimitIntervalSec=0

[Service]
User=dp
WorkingDirectory=/home/dp/tvPlayer
ExecStart=/usr/bin/python3 -u tvPlayer.py
Environment=XDG_RUNTIME_DIR=/run/user/1000
Restart=on-failure
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

`Environment=XDG_RUNTIME_DIR=/run/user/1000` is **not optional** — it is how mpv finds the user
PipeWire socket. Check the real uid with `id -u dp` first. Without it mpv cannot reach PipeWire
and there is no audio at all. `After=user@1000.service` makes sure the user's audio session is
up before tvPlayer starts (needs linger, see *Audio Setup* below).

Do **not** add `ExecStartPre`/`ExecStartPost` lines that restart PipeWire or WirePlumber — the
audio kick has to happen *after* mpv is running and is done inside `tvPlayer.py`.

Enable:
```bash
sudo systemctl enable tvplayer.service
```

---

# Audio Setup — Analog Jack + Connected HDMI at Once

Goal: audio plays simultaneously from the **3.5mm analog jack** and **whichever HDMI port has a
display**. Either port works, and moving the cable between ports at runtime works without
touching anything.

How it fits together:

- mpv plays to one PipeWire **combined sink** that mirrors audio to every real ALSA output.
- WirePlumber creates the HDMI sink for the port that has a display. It only probes the HDMI
  cards once, when it starts, so tvPlayer restarts WirePlumber after mpv is up (see *Hotplug*).
- **Volume and mute stay in tvPlayer.** mpv applies them in software before the audio reaches
  the combined sink, so the webremote level applies to all outputs equally. Leave `pactl`/
  `alsamixer` levels at 100%.

---

## Prerequisites

```bash
sudo apt install pipewire pipewire-pulse wireplumber pulseaudio-utils
```

Verify PipeWire is running:
```bash
pactl info | grep "Server Name"
# Should show: PulseAudio (on PipeWire ...)
```

Keep the user session (and with it PipeWire/WirePlumber) alive independent of tty logins:
```bash
sudo loginctl enable-linger dp
```

### Set HDMI Volume

WirePlumber defaults a never-seen HDMI output to 40%. Set each HDMI card to 100% once, with
tvPlayer running and the cable in that port (the sink only exists while a display is on it):

```bash
# cable in HDMI-A-1:
pactl set-sink-volume alsa_output.platform-fef00700.hdmi.hdmi-stereo 100%
# cable in HDMI-A-2 (after tvPlayer restarts):
pactl set-sink-volume alsa_output.platform-fef05700.hdmi.hdmi-stereo 100%
```

Stored in `~/.local/state/wireplumber/default-routes`; survives swaps and reboots.

---

## Combined Sink

```bash
mkdir -p ~/.config/pipewire/pipewire.conf.d
nano ~/.config/pipewire/pipewire.conf.d/combined-sink.conf
```

Paste:
```
context.modules = [
    {
        name = libpipewire-module-combine-stream
        args = {
            combine.mode = sink
            node.name = "combined-output"
            node.description = "HDMI + Analog Combined"
            combine.latency-compensate = true

            stream.rules = [
                {
                    matches = [
                        { media.class = "Audio/Sink" node.name = "~alsa_output.*" }
                    ]
                    actions = { create-stream = {} }
                }
            ]
        }
    }
]
```

The rule matches real ALSA sinks only (`alsa_output.*`), so the combined sink never tries to
feed itself. Sinks that appear later are picked up automatically.

Restart and set as default (WirePlumber remembers this across reboots):
```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
pactl set-default-sink combined-output
```

---

## Hotplug — Why tvPlayer Restarts WirePlumber

Two Pi 4 quirks, both handled in `system_init()`:

1. **WirePlumber probes the HDMI cards only once, at startup.** A port that had no display at
   that moment gets no `hdmi-stereo` profile, and plugging a display in later does not add it.
   Restarting WirePlumber re-probes. (Known issue, forum thread `t=343523`.)
2. **The HDMI audio stream must be opened after the display is on.** If WirePlumber opens the
   HDMI sink before mpv has set the video mode, the sink shows `RUNNING` but stays silent.

So `system_init()` waits until mpv reports video dimensions, then runs:
```python
subprocess.run(["systemctl", "--user", "restart", "wireplumber"], check=False, timeout=15)
```

Only WirePlumber restarts. PipeWire, the combined sink and mpv's connection to it all stay up,
so playback continues; the new HDMI sink is simply added to the combine. tvPlayer already exits
with code 75 when the HDMI connector changes and systemd restarts it, so every boot and every
cable move ends with a WirePlumber restart at the right moment.

---

## Verify

```bash
pactl list short sinks
```
Expected with one display connected:
```
combined-output
alsa_output.platform-fe00b840.mailbox.stereo-fallback        # analog
alsa_output.platform-fef00700.hdmi.hdmi-stereo               # HDMI-A-1 (fef05700 = HDMI-A-2)
```

Confirm mpv feeds the combined sink while tvPlayer runs:
```bash
pactl list short sink-inputs
```

Test the three cases: boot with cable in HDMI-A-1, boot with cable in HDMI-A-2, live swap.

