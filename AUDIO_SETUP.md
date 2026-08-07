# Audio Setup — Simultaneous HDMI + Analog Output

By default, mpv outputs audio to a single device. To get audio on **both HDMI and the 3.5mm analog jack simultaneously**, configure PipeWire with a combined sink.

---

## Prerequisites

```bash
sudo apt install pipewire pipewire-pulse wireplumber
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

This creates a virtual sink that mirrors audio to **all** available outputs (HDMI and analog).

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

## Verify

```bash
speaker-test -c 2 -t wav
```

You should hear audio from both HDMI and the analog jack.

---

## Notes

- If only one HDMI is connected, audio still goes to both HDMI and analog.
- The `combine-stream` module automatically picks up new sinks (e.g., when HDMI is hotplugged).
- mpv does not need any special audio configuration — it uses the system default sink.
- If PipeWire is not available, a similar setup is possible with PulseAudio's `module-combine-sink`.
