# Audio Setup — Sound Out of Every Output at Once

Goal: audio plays simultaneously from the **3.5mm analog jack** and **both HDMI ports**, so you
can plug into whichever you like and it just works.

By default mpv outputs to a single device. The fix is a PipeWire **combined sink**: one virtual
output that mirrors audio to every real output present on the system.

**Volume and mute stay in tvPlayer.** mpv applies them in software (`player.volume`) *before*
the audio reaches the combined sink, so whatever you set in the webremote applies to all outputs
equally. Do not use `pactl set-sink-volume` or `alsamixer` to control level — leave those at 100%
and let the webremote own it. Otherwise you end up with two independent volume stages fighting
each other.

---

## Prerequisites

```bash
sudo apt install pipewire pipewire-pulse wireplumber
sudo apt install pulseaudio-utils
```

Verify PipeWire is running:
```bash
pactl info | grep "Server Name"
# Should show: PulseAudio (on PipeWire ...)
```

---

## Create a Combined Sink

Create the config file:
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
                    matches = [ { media.class = "Audio/Sink" } ]
                    actions = { create-stream = {} }
                }
            ]
        }
    }
]
```

This mirrors audio to **all** available sinks. The `matches` rule deliberately targets every
`Audio/Sink` rather than naming devices, which matters for two reasons:

- On a Pi 4 the outputs appear as `vc4-hdmi0`, `vc4-hdmi1` and the analog `bcm2835-headphones` —
  naming them individually is brittle.
- **An HDMI sink only exists while a display is plugged in.** The `combine-stream` module picks up
  sinks as they appear and drops them as they vanish, so hotplugging a second screen adds its
  audio automatically with no reconfiguration.

---

## Set as Default

Restart PipeWire:
```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

List sinks and find the combined one:
```bash
pactl list short sinks
```

Set it as default:
```bash
pactl set-default-sink combined-output
```

To make it persistent across reboots, add to `~/.config/pipewire/pipewire.conf.d/default-sink.conf`:
```
context.properties = {
    default.audio.sink = "combined-output"
}
```

---

## Make it work under systemd

PipeWire runs as a **user** service, but tvPlayer is started by a system unit. Two things are
needed so the player can reach the user's audio session:

**1.** Keep the user session alive even when nobody is logged in:
```bash
sudo loginctl enable-linger dp
```

**2.** Confirm `tvplayer.service` runs as that same user (`User=dp`) and can see the session bus.
If audio is silent when started by systemd but works when run by hand, add to the `[Service]`
section:
```ini
Environment=XDG_RUNTIME_DIR=/run/user/1000
```
Check the real uid first with `id -u dp` — it is usually `1000`.

---

## Verify

List sinks and confirm the outputs are all there:
```bash
pactl list short sinks
```

Test the combined sink directly:
```bash
speaker-test -c 2 -t wav
```

You should hear audio from the analog jack and every connected HDMI display at once.

Then confirm mpv is actually feeding the combined sink while tvPlayer runs:
```bash
pactl list short sink-inputs
```

---

## Notes

- Only the outputs that physically exist produce sound. With one HDMI connected you get that HDMI
  plus analog; plug in the second and it joins automatically.
- mpv needs no special audio configuration — it follows the system default sink.
- HDMI audio needs `hdmi_drive=2` in `/boot/firmware/config.txt` on some setups. If HDMI is silent
  while analog works, check that first.
- `combine.latency-compensate = true` aligns the outputs. If you hear echo from having both a TV
  speaker and a jack-connected speaker in the same room, that is the physical distance between
  them, not a config problem.
- If PipeWire is unavailable, PulseAudio's `module-combine-sink` achieves the same thing.

---

## Status

**Untested.** Expect to iterate on this. `journalctl --user -u pipewire -n 50` is the first place
to look when something does not come up.
