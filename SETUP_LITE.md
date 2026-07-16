# Raspberry Pi OS Lite — Migration Checklist

Target: Raspberry Pi OS Lite (64-bit, Bookworm), headless, no desktop environment.  
mpv renders directly via DRM/KMS on tty1.

---

## Flash & First Boot

- Flash **Raspberry Pi OS Lite (64-bit, Bookworm)** via Raspberry Pi Imager
- In Imager advanced settings: set hostname, enable SSH, configure WiFi, create user (e.g. `pi`)
- Boot, SSH in

---

## User & Groups

```bash
sudo usermod -aG video,input,gpio,render,audio pi
```

---

## Autologin on tty1

Required for DRM/KMS access without a display manager.

```bash
sudo raspi-config
# System Options → Boot / Auto Login → Console Autologin
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
  hostapd dnsmasq
```

> `hostapd` / `dnsmasq` only needed if keeping the WiFi hotspot (alternative to RaspAP).

---

## Clone repo
```
git clone https://github.com/falue/tvPlayer.git
```


## Python Dependencies

```bash
pip install --break-system-packages python-mpv evdev natsort paho-mqtt flask RPi.GPIO
```

> `--break-system-packages` is required on Bookworm+ (PEP 668). Safe here since this is a single-purpose device.

---

## Network / Hotspot

Either:
- Reinstall RaspAP: `curl -sL https://install.raspap.com | bash`
- Or configure hostapd + dnsmasq manually for SSID `tvPlayer`

---

## Systemd Service

```ini
# /etc/systemd/system/tvplayer.service
[Unit]
Description=tvPlayer
After=multi-user.target

[Service]
User=pi
WorkingDirectory=/home/pi/tvPlayer
ExecStart=/usr/bin/python3 tvPlayer.py
Restart=on-failure
TTYPath=/dev/tty1
StandardInput=tty

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
